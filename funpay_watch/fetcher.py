"""Загрузка страницы предложений FunPay."""

import asyncio
from typing import Awaitable, Callable

import httpx

from funpay_watch.models import Offer
from funpay_watch.parser import parse_offers

CHIPS_URL = "https://funpay.com/chips/99/"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Ответы, означающие «притормози», а не «сломалось». Их лечит долгая пауза,
# а не повтор через секунду.
_THROTTLE_STATUSES = frozenset({403, 429, 503})


class FetchError(RuntimeError):
    """Страницу не удалось получить."""


class Throttled(FetchError):
    """FunPay ограничивает частоту запросов."""


class FunPayClient:
    def __init__(
        self,
        url: str = CHIPS_URL,
        http: httpx.AsyncClient | None = None,
        attempts: int = 3,
        retry_delay: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.url = url
        self.attempts = attempts
        self.retry_delay = retry_delay
        self.sleep = sleep
        self.http = http or httpx.AsyncClient(http2=True, timeout=20.0, follow_redirects=True)
        self.http.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        # Просим цены в долларах. Куку PHPSESSID сервер выдаст сам, и мы её
        # сохраним: живущая сессия выглядит естественнее новой каждые полминуты.
        self.http.cookies.set("cy", "usd", domain="funpay.com")

    async def __aenter__(self) -> "FunPayClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.http.aclose()

    async def fetch_offers(self) -> list[Offer]:
        return parse_offers(await self._get_html())

    async def _get_html(self) -> str:
        failure: FetchError | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = await self.http.get(self.url)
            except httpx.HTTPError as exc:
                failure = FetchError(f"запрос к FunPay не удался: {exc}")
            else:
                if response.status_code in _THROTTLE_STATUSES:
                    raise Throttled(f"FunPay ответил {response.status_code}")
                if response.status_code >= 500:
                    failure = FetchError(f"FunPay ответил {response.status_code}")
                elif response.status_code != 200:
                    raise FetchError(f"FunPay ответил {response.status_code}")
                else:
                    # Декодируем явно: страница всегда в UTF-8, а угадывание
                    # кодировки по заголовкам даёт разный результат.
                    return response.content.decode("utf-8")
            if attempt < self.attempts:
                await self.sleep(self.retry_delay * attempt)
        raise failure
