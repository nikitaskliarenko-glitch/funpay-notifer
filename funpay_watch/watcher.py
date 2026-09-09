"""Бесконечный цикл наблюдения с разбросом интервала и отступлением при сбоях."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Awaitable, Callable

from funpay_watch.poller import CycleResult, Poller

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Watcher:
    def __init__(
        self,
        poller: Poller,
        alert: Callable[[str], Awaitable[None]],
        interval: float = 30.0,
        jitter: float = 0.2,
        backoff_start: float = 60.0,
        backoff_max: float = 900.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.poller = poller
        self.alert = alert
        self.interval = interval
        self.jitter = jitter
        self.backoff_start = backoff_start
        self.backoff_max = backoff_max
        self.sleep = sleep
        self.now = now
        self.consecutive_failures = 0
        self.last_result: CycleResult | None = None
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    async def tick(self) -> float:
        """Выполняет один цикл и возвращает паузу до следующего."""
        moment = self.now()
        try:
            result = await self.poller.run_cycle(now=moment)
        except Exception as exc:
            self.consecutive_failures += 1
            self.last_error = str(exc)
            log.warning("цикл сорвался (подряд %d): %s", self.consecutive_failures, exc)
            # Пишем только о первом сбое подряд, иначе долгая недоступность
            # сайта превратится в поток одинаковых сообщений.
            if self.consecutive_failures == 1:
                await self.alert(f"Опрос FunPay сорвался: {exc}\nПродолжаю пробовать реже.")
            return min(self.backoff_start * 2 ** (self.consecutive_failures - 1), self.backoff_max)

        self.last_result = result
        self.last_success_at = moment
        self.last_error = None
        if self.consecutive_failures:
            self.consecutive_failures = 0
            await self.alert("FunPay снова отвечает, наблюдение идёт в обычном темпе.")
        return self.interval * random.uniform(1 - self.jitter, 1 + self.jitter)

    async def run_forever(self) -> None:
        while True:
            await self.sleep(await self.tick())
