"""Разбор HTML страницы предложений FunPay."""

import re
from decimal import Decimal

from selectolax.parser import HTMLParser, Node

from funpay_watch.models import Offer

# Сколько месяцев даёт одна единица стажа. Часы, дни и недели округляются вниз
# до нуля: FunPay и сам округляет вниз, так что фильтр «на сайте от N месяцев»
# получается консервативным в пользу покупателя.
_UNIT_MONTHS = {
    "час": 0, "часа": 0, "часов": 0,
    "день": 0, "дня": 0, "дней": 0,
    "неделю": 0, "недели": 0, "недель": 0,
    "месяц": 1, "месяца": 1, "месяцев": 1,
    "год": 12, "года": 12, "лет": 12,
}

_TENURE_RE = re.compile(r"на сайте\s+(?:(\d+)\s+)?(\w+)")
_STARS_CLASS_RE = re.compile(r"^rating-(\d)$")
_REVIEWS_TEXT_RE = re.compile(r"^(?:нет отзывов|(\d+) отзыв(?:а|ов)?)$")


def parse_tenure_months(text: str) -> int:
    """«на сайте 2 года» -> 24. Без числа единица считается за одну."""
    match = _TENURE_RE.search(text.strip())
    if match is None:
        raise ValueError(f"не удалось разобрать стаж: {text!r}")
    count = int(match.group(1)) if match.group(1) else 1
    unit = match.group(2)
    if unit not in _UNIT_MONTHS:
        raise ValueError(f"неизвестная единица стажа {unit!r} в {text!r}")
    return count * _UNIT_MONTHS[unit]


class ParseError(RuntimeError):
    """Страница не похожа на список предложений FunPay."""


def parse_offers(html: str) -> list[Offer]:
    """Собирает все предложения со страницы общего списка.

    Пустой результат считается ошибкой, а не отсутствием предложений: так
    смена вёрстки или страница технических работ не пройдёт молча дальше.
    """
    found: dict[str, Offer] = {}
    for node in HTMLParser(html).css("a.tc-item"):
        offer = _parse_row(node)
        # Проплаченное предложение FunPay показывает дважды: закреплённым
        # сверху и на своём месте в общей сортировке. Оставляем первое.
        found.setdefault(offer.offer_id, offer)
    if not found:
        raise ParseError("на странице нет ни одного предложения")
    return list(found.values())


def _parse_stars(node: Node) -> int:
    for token in node.attributes["class"].split():
        match = _STARS_CLASS_RE.match(token)
        if match:
            return int(match.group(1))
    raise ValueError(f"нет класса rating-N в {node.attributes['class']!r}")


def _parse_seller_rating(node: Node) -> tuple[int | None, int]:
    """Возвращает пару «звёзды, отзывы». Блок отзывов бывает трёх форм.

    Со звёздами и счётчиком, текстом «нет отзывов» и текстом «N отзывов».
    Звёзды появляются не сразу, поэтому их отсутствие это None, а не ноль:
    продавец без рейтинга не то же самое, что продавец с нулевым рейтингом.
    """
    block = node.css_first(".media-user-reviews")
    stars_node = block.css_first(".rating-stars")
    if stars_node is not None:
        return _parse_stars(stars_node), int(block.css_first(".rating-mini-count").text(strip=True))
    text = block.text(separator=" ", strip=True)
    match = _REVIEWS_TEXT_RE.match(text)
    if match is None:
        raise ValueError(f"не удалось разобрать блок отзывов: {text!r}")
    return None, int(match.group(1) or 0)


def _parse_row(node: Node) -> Offer:
    url = node.attributes["href"]
    offer_id = url.split("id=", 1)[1]
    price_node = node.css_first(".tc-price div")
    # Валюту сверяем на каждой строке: если кука cy потерялась, цены приедут
    # в рублях и молча пройдут порог, заданный в долларах.
    unit = price_node.css_first(".unit").text(strip=True)
    if unit != "$":
        raise ParseError(f"цены отдаются в другой валюте: {unit!r}, ожидался доллар")
    stars, reviews = _parse_seller_rating(node)
    tenure_text = node.css_first(".media-user-info").text(strip=True)
    return Offer(
        offer_id=offer_id,
        seller_id=int(offer_id.split("-", 1)[0]),
        seller_name=node.css_first(".media-user-name").text(strip=True),
        stars=stars,
        reviews=reviews,
        tenure_months=parse_tenure_months(tenure_text),
        tenure_text=tenure_text,
        # Наличие берём из data-s, а не из текста: в тексте бывает знак
        # бесконечности и неразрывные пробелы в разрядах тысяч.
        stock=int(node.css_first(".tc-amount").attributes["data-s"]),
        price_usd=Decimal(price_node.text(separator=" ", strip=True).split()[0]),
        # У офлайн-продавцов атрибута data-online нет вовсе, а не значение "0".
        online=node.attributes.get("data-online") == "1",
        method=node.css_first(".tc-server").text(strip=True),
        url=url,
    )


_MINIMUM_ORDER_RE = re.compile(r"Минимум\s+([\d.,]+)\s+ед\.")


def parse_minimum_order(html: str) -> Decimal | None:
    """Минимальный заказ со страницы предложения.

    В общем списке этого нет, а разброс большой: от единиц до тысяч. Дешёвое
    предложение с минимумом в 2500 единиц бесполезно, если нужно 500.
    """
    match = _MINIMUM_ORDER_RE.search(html)
    if match is None:
        return None
    return Decimal(match.group(1).replace(",", "."))
