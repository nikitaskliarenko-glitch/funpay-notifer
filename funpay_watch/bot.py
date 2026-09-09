"""Слой Telegram: разбирает команды и отдаёт ответы из actions."""

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import LinkPreviewOptions, Message

from funpay_watch import actions
from funpay_watch.actions import FetchOffers
from funpay_watch.storage import Storage
from funpay_watch.watcher import Watcher

log = logging.getLogger(__name__)

# Ссылок в ответах много, а превью FunPay раздувает переписку до бесполезности.
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def build_router(
    storage: Storage,
    fetch_offers: FetchOffers,
    watcher: Watcher,
    owner_id: int,
) -> Router:
    router = Router()
    # Вся защита бота держится на этой строке: сообщения от любого другого
    # пользователя не доходят ни до одного обработчика. Веб-поверхности,
    # которую пришлось бы защищать отдельно, у службы нет вовсе.
    router.message.filter(F.from_user.id == owner_id)

    @router.message(Command("start", "help"))
    async def start(message: Message) -> None:
        await message.answer(actions.handle_start(storage))

    @router.message(Command("filters"))
    async def show_filters(message: Message) -> None:
        await message.answer(actions.handle_filters(storage))

    @router.message(Command("set"))
    async def set_filter(message: Message, command: CommandObject) -> None:
        await message.answer(actions.handle_set(storage, command.args or ""))

    @router.message(Command("on"))
    async def switch_on(message: Message) -> None:
        try:
            replies = await actions.handle_on(storage, fetch_offers)
        except Exception as exc:
            log.warning("не удалось показать текущую картину: %s", exc)
            await message.answer(f"Поиск включён, но список сейчас не читается: {exc}")
            return
        for reply in replies:
            await message.answer(reply, link_preview_options=NO_PREVIEW)

    @router.message(Command("off"))
    async def switch_off(message: Message) -> None:
        await message.answer(actions.handle_off(storage))

    @router.message(Command("test"))
    async def dry_run(message: Message) -> None:
        try:
            reply = await actions.handle_test(storage, fetch_offers)
        except Exception as exc:
            reply = f"Список сейчас не читается: {exc}"
        await message.answer(reply, link_preview_options=NO_PREVIEW)

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        await message.answer(
            actions.handle_status(storage, watcher, now=datetime.now(timezone.utc))
        )

    return router
