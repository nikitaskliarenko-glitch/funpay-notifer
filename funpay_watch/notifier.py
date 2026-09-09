"""Текст уведомления и его отправка в Telegram."""

import asyncio
import logging
from decimal import Decimal
from typing import Awaitable, Callable

from funpay_watch.models import Offer

log = logging.getLogger(__name__)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Русская форма слова при числе: 1 отзыв, 2 отзыва, 5 отзывов."""
    if count % 100 in (11, 12, 13, 14):
        return many
    last = count % 10
    if last == 1:
        return one
    if last in (2, 3, 4):
        return few
    return many


def format_offer(offer: Offer, minimum_order: Decimal | None = None) -> str:
    """Собирает сообщение о предложении.

    Отправляем простым текстом без разметки: ник продавца может содержать
    подчёркивания и угловые скобки, которые сломали бы Markdown или HTML.
    """
    if offer.stars is None:
        rating = "без рейтинга"
    else:
        rating = f"{offer.stars} {plural(offer.stars, 'звезда', 'звезды', 'звёзд')}"
    reviews = f"{offer.reviews} {plural(offer.reviews, 'отзыв', 'отзыва', 'отзывов')}"
    stock = f"{offer.stock:,}".replace(",", " ")

    lines = [
        f"Robux ${offer.price_usd:.4f} за 1 шт.",
        f"Наличие: {stock} · {offer.method}",
        f"Продавец: {offer.seller_name} · {rating} · {reviews}"
        f" · {offer.tenure_text} · {'онлайн' if offer.online else 'офлайн'}",
    ]
    if minimum_order:
        lines.append(f"Минимальный заказ: {minimum_order} ед.")
    lines.append(offer.url)
    return "\n".join(lines)


class TelegramNotifier:
    """Отправляет сообщение сразу, а справку о минимальном заказе догоняет.

    Минимальный заказ живёт только на странице предложения, а её запрос стоит
    лишние доли секунды. Ждать их до отправки нельзя: смысл всей затеи в том,
    чтобы успеть раньше других покупателей.
    """

    def __init__(
        self,
        send: Callable[[str], Awaitable[int]],
        edit: Callable[[int, str], Awaitable[None]],
        fetch_minimum_order: Callable[[Offer], Awaitable[Decimal | None]] | None = None,
    ) -> None:
        self._send = send
        self._edit = edit
        self._fetch_minimum_order = fetch_minimum_order
        self._pending: set[asyncio.Task] = set()

    async def __call__(self, offer: Offer) -> None:
        message_id = await self._send(format_offer(offer))
        if self._fetch_minimum_order is None:
            return
        task = asyncio.create_task(self._append_minimum_order(message_id, offer))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _append_minimum_order(self, message_id: int, offer: Offer) -> None:
        try:
            minimum = await self._fetch_minimum_order(offer)
        except Exception as exc:
            log.warning("не удалось узнать минимальный заказ для %s: %s", offer.offer_id, exc)
            return
        if minimum is None:
            return
        try:
            await self._edit(message_id, format_offer(offer, minimum_order=minimum))
        except Exception as exc:
            log.warning("не удалось дописать минимальный заказ: %s", exc)

    async def drain(self) -> None:
        """Дожидается фоновых дополнений. Нужно тестам и остановке службы."""
        while self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
