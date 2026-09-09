from datetime import datetime, timezone
from decimal import Decimal

import pytest

from funpay_watch.models import Filters
from funpay_watch.poller import Poller
from funpay_watch.storage import Storage

from tests.test_matcher import make_offer

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

LOOSE = Filters(
    min_stock=1,
    min_stars=None,
    min_reviews=0,
    max_price=Decimal("0.0100"),
    min_tenure_months=0,
    only_online=False,
)


class FakeSource:
    """Отдаёт заранее заданный список предложений вместо запроса к сайту."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.batches[min(self.calls - 1, len(self.batches) - 1)]


class Recorder:
    def __init__(self):
        self.sent = []

    async def __call__(self, offer):
        self.sent.append(offer)


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path / "poll.db")
    storage.set_enabled(True)
    for name in ("min_stock", "min_stars", "min_reviews", "max_price", "min_tenure_months", "only_online"):
        storage.update_filter(name, getattr(LOOSE, name))
    yield storage
    storage.close()


def make_poller(store, source, recorder):
    return Poller(fetch_offers=source, storage=store, notify=recorder)


async def test_first_cycle_seeds_state_without_sending_anything(store):
    source = FakeSource([make_offer(price_usd=Decimal("0.0050"))])
    recorder = Recorder()

    result = await make_poller(store, source, recorder).run_cycle(now=NOW)

    assert recorder.sent == []
    assert result.matching == 1
    assert store.load_states()["123-141-99-2356-0"].matched is True


async def test_offer_that_becomes_matching_after_the_first_cycle_is_sent(store):
    expensive = make_offer(price_usd=Decimal("0.0200"))
    cheap = make_offer(price_usd=Decimal("0.0050"))
    source = FakeSource([expensive], [cheap])
    recorder = Recorder()
    poller = make_poller(store, source, recorder)

    await poller.run_cycle(now=NOW)
    await poller.run_cycle(now=NOW)

    assert [o.price_usd for o in recorder.sent] == [Decimal("0.0050")]


async def test_matching_offer_is_not_repeated_every_cycle(store):
    expensive = make_offer(price_usd=Decimal("0.0200"))
    cheap = make_offer(price_usd=Decimal("0.0050"))
    source = FakeSource([expensive], [cheap], [cheap], [cheap])
    recorder = Recorder()
    poller = make_poller(store, source, recorder)

    for _ in range(4):
        await poller.run_cycle(now=NOW)

    assert len(recorder.sent) == 1


async def test_offer_that_disappears_and_returns_is_sent_again(store):
    cheap = make_offer(price_usd=Decimal("0.0050"))
    other = make_offer(offer_id="999-141-99-2356-0", price_usd=Decimal("0.0200"))
    source = FakeSource([other], [cheap, other], [other], [cheap, other])
    recorder = Recorder()
    poller = make_poller(store, source, recorder)

    for _ in range(4):
        await poller.run_cycle(now=NOW)

    assert len(recorder.sent) == 2


async def test_disabled_search_never_touches_the_site(store):
    store.set_enabled(False)
    source = FakeSource([make_offer(price_usd=Decimal("0.0050"))])
    recorder = Recorder()

    result = await make_poller(store, source, recorder).run_cycle(now=NOW)

    assert result.ran is False
    assert source.calls == 0
    assert recorder.sent == []


async def test_failed_fetch_leaves_previous_state_untouched(store):
    cheap = make_offer(price_usd=Decimal("0.0050"))
    source = FakeSource([cheap])
    recorder = Recorder()
    poller = make_poller(store, source, recorder)
    await poller.run_cycle(now=NOW)
    before = store.load_states()

    async def broken():
        raise RuntimeError("сайт недоступен")

    poller.fetch_offers = broken
    with pytest.raises(RuntimeError):
        await poller.run_cycle(now=NOW)

    assert store.load_states() == before


async def test_a_flood_of_matches_is_capped_and_reported(store):
    """Слишком мягкие пороги не должны заливать чат и упираться в лимиты Telegram."""
    many = [
        make_offer(offer_id=f"{i}-141-99-2356-0", price_usd=Decimal("0.0010") + Decimal("0.0001") * i)
        for i in range(30)
    ]
    seed = make_offer(offer_id="seed", price_usd=Decimal("0.9000"))
    source = FakeSource([seed], many)
    recorder = Recorder()
    warnings = []

    async def alert(text):
        warnings.append(text)

    poller = Poller(
        fetch_offers=source, storage=store, notify=recorder, alert=alert, notify_limit=5
    )
    await poller.run_cycle(now=NOW)
    await poller.run_cycle(now=NOW)

    assert len(recorder.sent) == 5
    assert [o.price_usd for o in recorder.sent] == sorted(o.price_usd for o in recorder.sent)
    assert len(warnings) == 1
    assert "25" in warnings[0]


async def test_matches_within_the_cap_produce_no_warning(store):
    cheap = make_offer(price_usd=Decimal("0.0050"))
    seed = make_offer(offer_id="seed", price_usd=Decimal("0.9000"))
    source = FakeSource([seed], [cheap, seed])
    recorder = Recorder()
    warnings = []

    async def alert(text):
        warnings.append(text)

    poller = Poller(fetch_offers=source, storage=store, notify=recorder, alert=alert, notify_limit=5)
    await poller.run_cycle(now=NOW)
    await poller.run_cycle(now=NOW)

    assert len(recorder.sent) == 1
    assert warnings == []
