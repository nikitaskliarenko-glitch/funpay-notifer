from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from funpay_watch.models import OfferState
from funpay_watch.storage import Storage

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    storage = Storage(tmp_path / "test.db")
    yield storage
    storage.close()


def make_state(offer_id="a-1", matched=True, price="0.0080", notified="0.0080") -> OfferState:
    return OfferState(
        offer_id=offer_id,
        price_usd=Decimal(price),
        stock=50,
        matched=matched,
        last_notified_price=Decimal(notified) if notified else None,
    )


def test_fresh_database_returns_documented_default_filters(store):
    filters = store.get_filters()

    assert filters.min_stock == 1
    assert filters.min_stars == 4
    assert filters.min_reviews == 100
    assert filters.max_price == Decimal("0.0080")
    assert filters.min_tenure_months == 12
    assert filters.only_online is False


def test_search_is_off_until_switched_on(store):
    assert store.is_enabled() is False

    store.set_enabled(True)

    assert store.is_enabled() is True


def test_changed_filter_survives_reopening_the_database(tmp_path):
    first = Storage(tmp_path / "test.db")
    first.update_filter("max_price", Decimal("0.0075"))
    first.close()

    second = Storage(tmp_path / "test.db")
    try:
        assert second.get_filters().max_price == Decimal("0.0075")
    finally:
        second.close()


def test_offer_state_round_trips_through_the_database(store):
    store.save_cycle([make_state()], now=NOW)

    loaded = store.load_states()

    assert loaded["a-1"] == make_state()


def test_offer_missing_from_the_latest_cycle_stops_being_matched(store):
    store.save_cycle([make_state("a-1"), make_state("b-2")], now=NOW)

    store.save_cycle([make_state("a-1")], now=NOW + timedelta(seconds=30))

    loaded = store.load_states()
    assert loaded["a-1"].matched is True
    assert loaded["b-2"].matched is False


def test_offer_absent_for_longer_than_the_retention_window_is_pruned(store):
    store.save_cycle([make_state("a-1"), make_state("b-2")], now=NOW)

    store.save_cycle([make_state("a-1")], now=NOW + timedelta(days=8))
    removed = store.prune(older_than=timedelta(days=7), now=NOW + timedelta(days=8))

    assert removed == 1
    assert set(store.load_states()) == {"a-1"}


def test_clearing_state_makes_the_next_cycle_start_from_scratch(store):
    store.save_cycle([make_state("a-1")], now=NOW)

    store.clear_states()

    assert store.load_states() == {}
