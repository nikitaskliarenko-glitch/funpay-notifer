from decimal import Decimal

import pytest

from funpay_watch.models import Filters, Offer
from funpay_watch.matcher import matches


def make_offer(**overrides) -> Offer:
    """Предложение, проходящее фильтры из make_filters ровно по границе."""
    defaults = dict(
        offer_id="123-141-99-2356-0",
        seller_id=123,
        seller_name="Продавец",
        stars=4,
        reviews=100,
        tenure_months=12,
        tenure_text="на сайте год",
        stock=50,
        price_usd=Decimal("0.0080"),
        online=False,
        method="Game Pass (5 дней)",
        url="https://funpay.com/chips/offer?id=123-141-99-2356-0",
    )
    return Offer(**{**defaults, **overrides})


def make_filters(**overrides) -> Filters:
    defaults = dict(
        min_stock=50,
        min_stars=4,
        min_reviews=100,
        max_price=Decimal("0.0080"),
        min_tenure_months=12,
        only_online=False,
    )
    return Filters(**{**defaults, **overrides})


def test_offer_exactly_on_every_threshold_matches():
    assert matches(make_offer(), make_filters()) is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("stock", 49),
        ("stars", 3),
        ("reviews", 99),
        ("price_usd", Decimal("0.0081")),
        ("tenure_months", 11),
    ],
)
def test_offer_one_step_past_a_threshold_does_not_match(field, value):
    assert matches(make_offer(**{field: value}), make_filters()) is False


def test_seller_without_rating_never_passes_a_star_filter():
    """Отсутствие звёзд это не нулевой рейтинг, а его отсутствие."""
    assert matches(make_offer(stars=None), make_filters(min_stars=1)) is False


def test_seller_without_rating_passes_when_stars_are_not_required():
    assert matches(make_offer(stars=None), make_filters(min_stars=None)) is True


def test_offline_seller_is_rejected_only_when_online_is_required():
    assert matches(make_offer(online=False), make_filters(only_online=True)) is False
    assert matches(make_offer(online=True), make_filters(only_online=True)) is True
    assert matches(make_offer(online=False), make_filters(only_online=False)) is True
