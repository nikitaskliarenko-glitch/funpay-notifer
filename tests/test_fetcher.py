import httpx
import pytest

from funpay_watch.fetcher import FunPayClient, FetchError, Throttled

URL = "https://funpay.com/chips/99/"


def client_with(handler, **kwargs) -> FunPayClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FunPayClient(url=URL, http=http, sleep=_no_wait, **kwargs)


async def _no_wait(_seconds):
    return None


async def test_asks_funpay_for_prices_in_dollars(live_page):
    seen = {}

    def handler(request):
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, text=live_page)

    async with client_with(handler) as client:
        await client.fetch_offers()

    assert "cy=usd" in seen["cookie"]


async def test_returns_offers_parsed_from_the_page(live_page):
    async with client_with(lambda r: httpx.Response(200, text=live_page)) as client:
        offers = await client.fetch_offers()

    assert len(offers) == 597


async def test_retries_a_failing_request_and_succeeds(live_page):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("сеть отвалилась")
        return httpx.Response(200, text=live_page)

    async with client_with(handler, attempts=3) as client:
        offers = await client.fetch_offers()

    assert len(calls) == 3
    assert len(offers) == 597


async def test_gives_up_after_the_last_attempt(live_page):
    def handler(request):
        raise httpx.ConnectError("сеть отвалилась")

    async with client_with(handler, attempts=2) as client:
        with pytest.raises(FetchError):
            await client.fetch_offers()


@pytest.mark.parametrize("status", [403, 429, 503])
async def test_rate_limiting_responses_are_reported_separately(status):
    def handler(request):
        return httpx.Response(status, text="")

    async with client_with(handler, attempts=1) as client:
        with pytest.raises(Throttled):
            await client.fetch_offers()


async def test_server_error_is_retried_then_reported(live_page):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, text="")

    async with client_with(handler, attempts=3) as client:
        with pytest.raises(FetchError):
            await client.fetch_offers()

    assert len(calls) == 3
