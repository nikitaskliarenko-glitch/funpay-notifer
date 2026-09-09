from decimal import Decimal

import pytest

from funpay_watch.commands import parse_filter_value, render_filters, render_matches
from funpay_watch.storage import DEFAULT_FILTERS

from tests.test_matcher import make_offer


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("min_stock", "500", 500),
        ("min_reviews", "0", 0),
        ("min_tenure_months", "24", 24),
        ("max_price", "0.0075", Decimal("0.0075")),
        ("min_stars", "5", 5),
        ("min_stars", "нет", None),
        ("only_online", "да", True),
        ("only_online", "нет", False),
    ],
)
def test_accepts_a_valid_filter_value(name, raw, expected):
    assert parse_filter_value(name, raw) == expected


@pytest.mark.parametrize(
    "name,raw",
    [
        ("min_stock", "-1"),
        ("min_stock", "много"),
        ("min_reviews", "1.5"),
        ("max_price", "0"),
        ("max_price", "дёшево"),
        ("min_stars", "6"),
        ("min_stars", "0"),
        ("only_online", "может быть"),
    ],
)
def test_rejects_an_impossible_filter_value(name, raw):
    with pytest.raises(ValueError):
        parse_filter_value(name, raw)


def test_unknown_filter_name_is_rejected_and_lists_the_real_ones():
    with pytest.raises(ValueError, match="max_price"):
        parse_filter_value("цена", "1")


def test_filter_listing_names_every_threshold_and_the_search_state():
    text = render_filters(DEFAULT_FILTERS, enabled=False)

    for name in ("min_stock", "min_stars", "min_reviews", "max_price", "min_tenure_months", "only_online"):
        assert name in text
    assert "выключен" in text


def test_filter_listing_shows_an_unset_star_threshold_as_not_checked():
    from dataclasses import replace

    text = render_filters(replace(DEFAULT_FILTERS, min_stars=None), enabled=True)

    assert "не проверяется" in text
    assert "включён" in text


def test_match_listing_shows_the_cheapest_offers_first():
    offers = [
        make_offer(offer_id="a", price_usd=Decimal("0.0090")),
        make_offer(offer_id="b", price_usd=Decimal("0.0070")),
        make_offer(offer_id="c", price_usd=Decimal("0.0080")),
    ]

    text = render_matches(offers, limit=2)

    assert text.index("0.0070") < text.index("0.0080")
    assert "0.0090" not in text


def test_empty_match_listing_says_so():
    assert "ничего" in render_matches([], limit=5).lower()


def test_match_listing_also_pads_prices_to_four_decimals():
    text = render_matches([make_offer(price_usd=Decimal("0.008"))], limit=5)

    assert "$0.0080" in text
