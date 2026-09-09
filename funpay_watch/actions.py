"""Что бот отвечает на каждую команду.

Здесь нет ни одного вызова Telegram: слой aiogram только передаёт сюда текст
команды и отправляет полученную строку. Так поведение команд проверяется
тестами напрямую, без бота и сети.
"""

from datetime import datetime
from typing import Awaitable, Callable

from funpay_watch.commands import parse_filter_value, render_filters, render_matches
from funpay_watch.matcher import matches
from funpay_watch.models import Offer
from funpay_watch.notifier import plural
from funpay_watch.storage import Storage

FetchOffers = Callable[[], Awaitable[list[Offer]]]

SET_FORMAT = "Формат: /set max_price 0.0075\nСписок порогов: /filters"

HELP = (
    "Слежу за списком робуксов на FunPay и пишу, когда появляется подходящее "
    "предложение.\n\n"
    "/filters — показать пороги\n"
    "/set поле значение — изменить порог\n"
    "/on — включить поиск\n"
    "/off — выключить поиск\n"
    "/test — что подходит прямо сейчас\n"
    "/status — как идут дела"
)


def handle_start(storage: Storage) -> str:
    return f"{HELP}\n\n{handle_filters(storage)}"


def handle_filters(storage: Storage) -> str:
    return render_filters(storage.get_filters(), enabled=storage.is_enabled())


def handle_set(storage: Storage, args: str) -> str:
    parts = args.split(maxsplit=1)
    if len(parts) != 2:
        return SET_FORMAT
    name, raw = parts
    try:
        value = parse_filter_value(name, raw)
    except ValueError as exc:
        return str(exc)
    storage.update_filter(name, value)
    return f"Порог {name} обновлён.\n\n{handle_filters(storage)}"


async def _summarise(storage: Storage, fetch_offers: FetchOffers, limit: int = 5) -> str:
    offers = await fetch_offers()
    good = [offer for offer in offers if matches(offer, storage.get_filters())]
    return f"Сейчас подходит {len(good)} из {len(offers)}.\n\n{render_matches(good, limit=limit)}"


async def handle_on(storage: Storage, fetch_offers: FetchOffers) -> list[str]:
    storage.set_enabled(True)
    # Забываем прошлую выдачу, иначе после долгой паузы прилетит лавина
    # сообщений обо всём, что успело подешеветь. Первый цикл пройдёт молча,
    # а текущую картину показываем прямо сейчас, отдельным сообщением.
    storage.clear_states()
    return [
        "Поиск включён. Первый цикл только запомнит выдачу, сообщения пойдут дальше.",
        await _summarise(storage, fetch_offers),
    ]


def handle_off(storage: Storage) -> str:
    storage.set_enabled(False)
    return "Поиск выключен."


async def handle_test(storage: Storage, fetch_offers: FetchOffers) -> str:
    return await _summarise(storage, fetch_offers)


def handle_status(storage: Storage, watcher, now: datetime) -> str:
    lines = ["Поиск включён." if storage.is_enabled() else "Поиск выключен."]

    if watcher.last_success_at is None:
        lines.append("Успешных опросов ещё не было.")
    else:
        ago = int((now - watcher.last_success_at).total_seconds())
        result = watcher.last_result
        lines.append(f"Последний успешный опрос: {ago} {plural(ago, 'секунду', 'секунды', 'секунд')} назад.")
        if result is not None:
            lines.append(f"Предложений в списке: {result.total}, подходит: {result.matching}.")

    if watcher.last_error:
        failures = watcher.consecutive_failures
        lines.append(
            f"Сейчас не отвечает: {watcher.last_error}"
            f"\nСбоев подряд: {failures}."
        )
    return "\n".join(lines)
