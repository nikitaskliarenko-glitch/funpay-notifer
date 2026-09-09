import pytest

from funpay_watch.fetcher import Throttled
from funpay_watch.poller import CycleResult
from funpay_watch.watcher import Watcher


class StubPoller:
    """Отдаёт заранее заданные исходы циклов: результат или исключение."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def run_cycle(self, now):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Alerts:
    def __init__(self):
        self.messages = []

    async def __call__(self, text):
        self.messages.append(text)


OK = CycleResult(ran=True, total=597, matching=3, notified=0)
IDLE = CycleResult(ran=False)


def make_watcher(poller, alerts, **kwargs):
    return Watcher(poller=poller, alert=alerts, interval=30.0, **kwargs)


async def test_successful_cycle_waits_about_the_normal_interval():
    watcher = make_watcher(StubPoller(OK), Alerts())

    delay = await watcher.tick()

    assert 24.0 <= delay <= 36.0


async def test_interval_is_jittered_rather_than_fixed():
    watcher = make_watcher(StubPoller(OK), Alerts())

    delays = {await watcher.tick() for _ in range(10)}

    assert len(delays) > 1


async def test_disabled_search_still_waits_the_normal_interval():
    watcher = make_watcher(StubPoller(IDLE), Alerts())

    assert 24.0 <= await watcher.tick() <= 36.0


async def test_failures_back_off_exponentially_up_to_the_cap():
    watcher = make_watcher(
        StubPoller(Throttled("429")), Alerts(), backoff_start=60.0, backoff_max=900.0
    )

    delays = [await watcher.tick() for _ in range(6)]

    assert delays == [60.0, 120.0, 240.0, 480.0, 900.0, 900.0]


async def test_only_the_first_failure_in_a_row_is_reported():
    alerts = Alerts()
    watcher = make_watcher(StubPoller(Throttled("429")), alerts)

    for _ in range(4):
        await watcher.tick()

    assert len(alerts.messages) == 1
    assert "429" in alerts.messages[0]


async def test_recovery_is_reported_and_clears_the_backoff():
    alerts = Alerts()
    watcher = make_watcher(StubPoller(Throttled("429"), Throttled("429"), OK, OK), alerts)

    await watcher.tick()
    await watcher.tick()
    recovered = await watcher.tick()

    assert len(alerts.messages) == 2
    assert "снова" in alerts.messages[1]
    assert 24.0 <= recovered <= 36.0


async def test_a_run_that_never_failed_reports_nothing():
    alerts = Alerts()
    watcher = make_watcher(StubPoller(OK), alerts)

    for _ in range(3):
        await watcher.tick()

    assert alerts.messages == []


async def test_watcher_remembers_the_last_successful_cycle_for_status():
    from datetime import datetime, timezone

    moment = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    watcher = make_watcher(StubPoller(OK), Alerts(), now=lambda: moment)

    await watcher.tick()

    assert watcher.last_result == OK
    assert watcher.last_success_at == moment
    assert watcher.last_error is None
    assert watcher.consecutive_failures == 0


async def test_watcher_remembers_why_the_last_cycle_failed():
    watcher = make_watcher(StubPoller(Throttled("429")), Alerts())

    await watcher.tick()

    assert "429" in watcher.last_error
    assert watcher.consecutive_failures == 1
    assert watcher.last_success_at is None
