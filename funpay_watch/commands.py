"""Разбор и отрисовка того, что бот показывает в чате."""

from decimal import Decimal, InvalidOperation

from funpay_watch.models import Filters, Offer
from funpay_watch.storage import FILTER_NAMES

_YES = {"да", "вкл", "on", "1", "true"}
_NO = {"нет", "выкл", "off", "0", "false"}
_UNSET = {"нет", "любой", "off", "-"}

# Человеческое название и единица для каждого порога.
LABELS = {
    "min_stock": "наличие от",
    "min_stars": "звёзды от",
    "min_reviews": "отзывов от",
    "max_price": "цена до, $",
    "min_tenure_months": "на сайте от, мес.",
    "only_online": "только онлайн",
}


def _count(raw: str) -> int:
    if not raw.isdigit():
        raise ValueError(f"нужно целое число не меньше нуля, а не {raw!r}")
    return int(raw)


def _stars(raw: str) -> int | None:
    if raw.lower() in _UNSET:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= 5:
        raise ValueError("звёзды задаются числом от 1 до 5 или словом «нет»")
    return int(raw)


def _price(raw: str) -> Decimal:
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"цена задаётся числом, например 0.0075, а не {raw!r}") from None
    if value <= 0:
        raise ValueError("цена должна быть больше нуля")
    return value


def _flag(raw: str) -> bool:
    lowered = raw.lower()
    if lowered in _YES:
        return True
    if lowered in _NO:
        return False
    raise ValueError("ответ задаётся словом «да» или «нет»")


_PARSERS = {
    "min_stock": _count,
    "min_reviews": _count,
    "min_tenure_months": _count,
    "min_stars": _stars,
    "max_price": _price,
    "only_online": _flag,
}


def parse_filter_value(name: str, raw: str):
    """Превращает текст из команды в значение фильтра."""
    parser = _PARSERS.get(name)
    if parser is None:
        raise ValueError(f"неизвестный фильтр {name!r}. Есть такие: {', '.join(FILTER_NAMES)}")
    return parser(raw.strip())


def _show(name: str, value) -> str:
    if name == "min_stars" and value is None:
        return "не проверяется"
    if name == "only_online":
        return "да" if value else "нет"
    return str(value)


def render_filters(filters: Filters, enabled: bool) -> str:
    width = max(len(name) for name in FILTER_NAMES)
    rows = "\n".join(
        f"{name:<{width}}  {_show(name, getattr(filters, name)):>8}  {LABELS[name]}"
        for name in FILTER_NAMES
    )
    state = "включён" if enabled else "выключен"
    return f"Поиск {state}.\n\n{rows}\n\nИзменить: /set max_price 0.0075"


def render_matches(offers: list[Offer], limit: int) -> str:
    if not offers:
        return "Сейчас под фильтры не подходит ничего."
    cheapest = sorted(offers, key=lambda o: o.price_usd)[:limit]
    lines = []
    for offer in cheapest:
        stars = "без рейтинга" if offer.stars is None else f"{offer.stars}\u2605"
        stock = f"{offer.stock:,}".replace(",", " ")
        lines.append(
            f"${offer.price_usd:.4f} · {stock} шт · {offer.seller_name}"
            f" · {stars} · {offer.reviews} отз.\n{offer.url}"
        )
    return "\n\n".join(lines)
