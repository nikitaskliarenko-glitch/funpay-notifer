"""Цикл наблюдения: сверить выдачу с порогами и отдать новые совпадения."""

from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from funpay_watch.matcher import matches
from funpay_watch.models import Offer, OfferState
from funpay_watch.storage import Storage
from funpay_watch.transitions import should_notify


@dataclass(frozen=True, slots=True)
class CycleResult:
    ran: bool
    total: int = 0
    matching: int = 0
    notified: int = 0


class Poller:
    def __init__(
        self,
        fetch_offers: Callable[[], Awaitable[list[Offer]]],
        storage: Storage,
        notify: Callable[[Offer], Awaitable[None]],
        alert: Callable[[str], Awaitable[None]] | None = None,
        notify_limit: int = 20,
    ) -> None:
        self.fetch_offers = fetch_offers
        self.storage = storage
        self.notify = notify
        self.alert = alert
        self.notify_limit = notify_limit

    async def run_cycle(self, now: datetime) -> CycleResult:
        if not self.storage.is_enabled():
            return CycleResult(ran=False)

        offers = await self.fetch_offers()
        filters = self.storage.get_filters()
        previous = self.storage.load_states()
        # Пустое состояние означает первый цикл. Тогда мы только запоминаем
        # выдачу, иначе на старте прилетит лавина обо всех подходящих сразу.
        seeding = not previous

        states: list[OfferState] = []
        to_send: list[Offer] = []
        matching = 0
        for offer in offers:
            now_matches = matches(offer, filters)
            matching += now_matches
            before = previous.get(offer.offer_id)
            send = not seeding and should_notify(before, offer, now_matches)
            if send:
                to_send.append(offer)
            states.append(
                OfferState(
                    offer_id=offer.offer_id,
                    price_usd=offer.price_usd,
                    stock=offer.stock,
                    matched=now_matches,
                    last_notified_price=(
                        offer.price_usd if send else (before.last_notified_price if before else None)
                    ),
                )
            )

        # Сначала отправка, потом запись. Если Telegram недоступен, цикл
        # оборвётся до сохранения и следующий проход попробует снова:
        # повтор сообщения безобиден, потерянное сообщение нет.
        # Слишком мягкие пороги дают сотни совпадений за цикл. Показываем
        # самые дешёвые, об остальных сообщаем одной строкой: иначе чат
        # заливает, а Telegram начинает резать частоту отправки.
        to_send.sort(key=lambda offer: offer.price_usd)
        shown, hidden = to_send[: self.notify_limit], to_send[self.notify_limit :]
        for offer in shown:
            await self.notify(offer)
        if hidden and self.alert is not None:
            await self.alert(
                f"Ещё {len(hidden)} подходящих предложений не показаны: пороги слишком"
                " мягкие. Ужесточите их командой /set, иначе выгодное утонет в потоке."
            )
        self.storage.save_cycle(states, now=now)

        return CycleResult(ran=True, total=len(offers), matching=matching, notified=len(shown))
