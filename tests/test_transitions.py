from decimal import Decimal

from funpay_watch.models import OfferState
from funpay_watch.transitions import should_notify

from tests.test_matcher import make_offer


def state(**overrides) -> OfferState:
    defaults = dict(
        offer_id="123-141-99-2356-0",
        price_usd=Decimal("0.0080"),
        stock=50,
        matched=True,
        last_notified_price=Decimal("0.0080"),
    )
    return OfferState(**{**defaults, **overrides})


def test_offer_seen_for_the_first_time_and_matching_is_notified():
    assert should_notify(None, make_offer(), now_matches=True) is True


def test_offer_seen_for_the_first_time_but_not_matching_is_silent():
    assert should_notify(None, make_offer(), now_matches=False) is False


def test_offer_that_just_became_matching_is_notified():
    previous = state(matched=False, last_notified_price=None)

    assert should_notify(previous, make_offer(), now_matches=True) is True


def test_still_matching_at_the_same_price_is_not_notified_again():
    assert should_notify(state(), make_offer(), now_matches=True) is False


def test_small_further_price_drop_is_not_notified_again():
    """Порог повтора пять процентов, падение на четыре его не проходит."""
    cheaper = make_offer(price_usd=Decimal("0.00768"))

    assert should_notify(state(), cheaper, now_matches=True) is False


def test_price_drop_of_five_percent_is_notified_again():
    cheaper = make_offer(price_usd=Decimal("0.0076"))

    assert should_notify(state(), cheaper, now_matches=True) is True


def test_offer_that_stopped_matching_is_silent():
    assert should_notify(state(), make_offer(stock=0), now_matches=False) is False
