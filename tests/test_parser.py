import pytest

from funpay_watch.parser import parse_tenure_months


@pytest.mark.parametrize(
    "text,expected",
    [
        # часы, дни и недели округляются вниз до нуля месяцев
        ("на сайте 2 часа", 0),
        ("на сайте 8 часов", 0),
        ("на сайте день", 0),
        ("на сайте 2 дня", 0),
        ("на сайте 3 дня", 0),
        ("на сайте 6 дней", 0),
        ("на сайте неделю", 0),
        ("на сайте 2 недели", 0),
        ("на сайте 3 недели", 0),
        # месяцы
        ("на сайте месяц", 1),
        ("на сайте 2 месяца", 2),
        ("на сайте 3 месяца", 3),
        ("на сайте 4 месяца", 4),
        ("на сайте 5 месяцев", 5),
        ("на сайте 6 месяцев", 6),
        ("на сайте 7 месяцев", 7),
        ("на сайте 8 месяцев", 8),
        ("на сайте 9 месяцев", 9),
        ("на сайте 10 месяцев", 10),
        ("на сайте 11 месяцев", 11),
        # годы
        ("на сайте год", 12),
        ("на сайте 2 года", 24),
        ("на сайте 3 года", 36),
        ("на сайте 4 года", 48),
        ("на сайте 5 лет", 60),
        ("на сайте 6 лет", 72),
        ("на сайте 7 лет", 84),
        ("на сайте 8 лет", 96),
        ("на сайте 9 лет", 108),
        ("на сайте 10 лет", 120),
        ("на сайте 11 лет", 132),
    ],
)
def test_parses_seller_tenure_into_months(text, expected):
    assert parse_tenure_months(text) == expected


def test_parses_offer_row_with_stars_and_review_count(row):
    from decimal import Decimal

    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("stars_and_reviews"))[0]

    assert offer.offer_id == "4808962-141-99-2356-0"
    assert offer.seller_id == 4808962
    assert offer.seller_name == "LukChug"
    assert offer.stars == 5
    assert offer.reviews == 1421
    assert offer.tenure_months == 48
    assert offer.stock == 3150
    assert offer.price_usd == Decimal("0.0087")
    assert offer.online is True
    assert offer.method == "Game Pass (5 дней)"
    assert offer.url == "https://funpay.com/chips/offer?id=4808962-141-99-2356-0"


def test_seller_without_rating_has_no_stars_and_zero_reviews(row):
    from decimal import Decimal

    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("no_reviews_infinite_stock"))[0]

    assert offer.seller_name == "WorldOfTanksEU9"
    assert offer.stars is None
    assert offer.reviews == 0
    assert offer.tenure_months == 3
    assert offer.price_usd == Decimal("0.0092")


def test_seller_with_few_reviews_has_reviews_but_no_stars(row):
    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("few_reviews_no_rating"))[0]

    assert offer.seller_name == "PrestigeSeller"
    assert offer.stars is None
    assert offer.reviews == 5


def test_reads_unlimited_stock_from_data_attribute_not_infinity_sign(row):
    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("no_reviews_infinite_stock"))[0]

    assert offer.stock == 10_000_000


def test_missing_data_online_attribute_means_seller_is_offline(row):
    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("offline_seller"))[0]

    assert offer.seller_name == "vit09092011"
    assert offer.online is False
    assert offer.stars == 3
    assert offer.reviews == 0


def test_parses_every_offer_on_live_page_snapshot(live_page):
    from funpay_watch.parser import parse_offers

    offers = parse_offers(live_page)

    assert len(offers) == 597
    assert len({o.offer_id for o in offers}) == 597
    assert all(o.price_usd > 0 for o in offers)
    assert all(o.stock >= 0 for o in offers)
    assert all(o.reviews >= 0 for o in offers)
    assert all(o.tenure_months >= 0 for o in offers)
    assert all(o.stars is None or 1 <= o.stars <= 5 for o in offers)
    assert all(o.seller_name for o in offers)
    assert all(o.url.startswith("https://funpay.com/chips/offer?id=") for o in offers)


def test_rejects_page_whose_prices_are_not_in_dollars(row):
    from funpay_watch.parser import ParseError, parse_offers

    in_euro = row("stars_and_reviews").replace(
        '<span class="unit">$</span>', '<span class="unit">€</span>'
    )

    with pytest.raises(ParseError, match="валют"):
        parse_offers(in_euro)


def test_rejects_page_without_any_offer_rows():
    from funpay_watch.parser import ParseError, parse_offers

    with pytest.raises(ParseError, match="ни одного предложения"):
        parse_offers("<html><body><p>Технические работы</p></body></html>")


def test_promoted_offer_pinned_on_top_is_not_returned_twice(live_page):
    """FunPay закрепляет проплаченное предложение сверху и повторяет его ниже."""
    import re

    from funpay_watch.parser import parse_offers

    rows_in_html = re.findall(r'chips/offer\?id=([^"]+)" class="tc-item', live_page)
    promoted = [i for i in rows_in_html if rows_in_html.count(i) > 1]
    assert promoted, "в снимке страницы нет закреплённого предложения"

    offers = parse_offers(live_page)

    assert len(offers) == len(set(rows_in_html))
    assert sum(1 for o in offers if o.offer_id == promoted[0]) == 1


def test_offer_keeps_the_original_tenure_text_for_display(row):
    """В месяцах «на сайте 3 недели» превращается в ноль, а показать надо как есть."""
    from funpay_watch.parser import parse_offers

    offer = parse_offers(row("stars_and_reviews"))[0]

    assert offer.tenure_text == "на сайте 4 года"


def test_reads_the_minimum_order_from_an_offer_page():
    import pathlib
    from decimal import Decimal

    from funpay_watch.parser import parse_minimum_order

    html = (pathlib.Path(__file__).parent / "fixtures" / "offer_page.html").read_text(
        encoding="utf-8"
    )

    assert parse_minimum_order(html) == Decimal("8")


def test_offer_page_without_a_minimum_order_yields_nothing():
    from funpay_watch.parser import parse_minimum_order

    assert parse_minimum_order("<html><body><form></form></body></html>") is None
