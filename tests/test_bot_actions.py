from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from funpay_watch.actions import handle_off, handle_on, handle_set, handle_status, handle_test
from funpay_watch.poller import CycleResult
from funpay_watch.storage import Storage

from tests.test_matcher import make_offer

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path / "bot.db")
    yield storage
    storage.close()


class StubWatcher:
    def __init__(self, **kwargs):
        self.last_result = kwargs.get("last_result")
        self.last_success_at = kwargs.get("last_success_at")
        self.last_error = kwargs.get("last_error")
        self.consecutive_failures = kwargs.get("consecutive_failures", 0)


async def offers_now():
    return [
        make_offer(offer_id="a", price_usd=Decimal("0.0070"), reviews=500),
        make_offer(offer_id="b", price_usd=Decimal("0.5000"), reviews=500),
    ]


def test_setting_a_filter_stores_it_and_confirms(store):
    reply = handle_set(store, "max_price 0.0075")

    assert store.get_filters().max_price == Decimal("0.0075")
    assert "max_price" in reply


def test_setting_an_unknown_filter_changes_nothing(store):
    before = store.get_filters()

    reply = handle_set(store, "цена 0.0075")

    assert store.get_filters() == before
    assert "неизвестный фильтр" in reply


def test_setting_a_bad_value_changes_nothing(store):
    before = store.get_filters()

    reply = handle_set(store, "min_stars 9")

    assert store.get_filters() == before
    assert "от 1 до 5" in reply


def test_set_without_arguments_shows_the_format(store):
    reply = handle_set(store, "")

    assert "/set max_price" in reply


async def test_switching_on_clears_state_so_the_first_cycle_stays_quiet(store):
    store.save_cycle([], now=NOW)
    store.update_filter("min_reviews", 0)

    replies = await handle_on(store, offers_now)

    assert store.is_enabled() is True
    assert store.load_states() == {}
    assert any("0.0070" in r for r in replies)
    assert any("подходит 1 из 2" in r for r in replies)


async def test_switching_off_stops_the_search(store):
    store.set_enabled(True)

    reply = handle_off(store)

    assert store.is_enabled() is False
    assert "выключен" in reply


async def test_test_command_reports_matches_without_enabling_anything(store):
    reply = await handle_test(store, offers_now)

    assert store.is_enabled() is False
    assert "подходит 1 из 2" in reply


def test_status_before_the_first_cycle_says_there_is_nothing_yet(store):
    reply = handle_status(store, StubWatcher(), now=NOW)

    assert "ещё не было" in reply


def test_status_reports_the_last_successful_cycle(store):
    watcher = StubWatcher(
        last_result=CycleResult(ran=True, total=597, matching=3, notified=1),
        last_success_at=NOW - timedelta(seconds=18),
    )

    reply = handle_status(store, watcher, now=NOW)

    assert "597" in reply
    assert "3" in reply
    assert "18" in reply


def test_status_surfaces_the_current_failure(store):
    watcher = StubWatcher(last_error="FunPay ответил 429", consecutive_failures=4)

    reply = handle_status(store, watcher, now=NOW)

    assert "429" in reply
    assert "4" in reply
