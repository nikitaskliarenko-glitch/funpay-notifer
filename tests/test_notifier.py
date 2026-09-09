from decimal import Decimal

import pytest

from funpay_watch.notifier import format_offer, plural

from tests.test_matcher import make_offer


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, "отзывов"),
        (1, "отзыв"),
        (2, "отзыва"),
        (4, "отзыва"),
        (5, "отзывов"),
        (11, "отзывов"),
        (14, "отзывов"),
        (21, "отзыв"),
        (64, "отзыва"),
        (114, "отзывов"),
        (122, "отзыва"),
        (1421, "отзыв"),
    ],
)
def test_picks_the_right_russian_plural_form(count, expected):
    assert plural(count, "отзыв", "отзыва", "отзывов") == expected


def test_message_carries_price_stock_seller_and_link():
    offer = make_offer(
        seller_name="Tvim0n",
        stars=5,
        reviews=64,
        tenure_text="на сайте 3 года",
        stock=2,
        price_usd=Decimal("0.0065"),
        online=True,
        method="Game Pass (5 дней)",
        url="https://funpay.com/chips/offer?id=8381848-141-99-2356-0",
    )

    text = format_offer(offer)

    assert text == (
        "Robux $0.0065 за 1 шт.\n"
        "Наличие: 2 · Game Pass (5 дней)\n"
        "Продавец: Tvim0n · 5 звёзд · 64 отзыва · на сайте 3 года · онлайн\n"
        "https://funpay.com/chips/offer?id=8381848-141-99-2356-0"
    )


def test_offline_seller_is_labelled_offline():
    text = format_offer(make_offer(online=False))

    assert "офлайн" in text
    assert "онлайн" not in text


def test_seller_without_rating_is_shown_as_having_none():
    text = format_offer(make_offer(stars=None, reviews=0))

    assert "без рейтинга" in text
    assert "0 отзывов" in text


def test_large_stock_is_grouped_for_readability():
    text = format_offer(make_offer(stock=3150))

    assert "Наличие: 3 150" in text


def test_minimum_order_is_appended_only_when_it_is_known():
    offer = make_offer()

    assert "Минимальный заказ" not in format_offer(offer)
    assert "Минимальный заказ: 2 ед." in format_offer(offer, minimum_order=Decimal("2"))


def test_minimum_order_line_sits_above_the_link():
    text = format_offer(make_offer(), minimum_order=Decimal("2500")).splitlines()

    assert text[-2] == "Минимальный заказ: 2500 ед."
    assert text[-1].startswith("https://")


def test_price_is_always_shown_with_four_decimals():
    """FunPay печатает то 0.008, то 0.0080. В списке разнобой мешает сравнивать."""
    assert "Robux $0.0080 за 1 шт." in format_offer(make_offer(price_usd=Decimal("0.008")))
