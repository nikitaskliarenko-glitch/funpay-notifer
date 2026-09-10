"""Точка входа: собирает службу и запускает бота вместе с наблюдателем."""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import Bot, Dispatcher
from aiogram.types import LinkPreviewOptions
from dotenv import load_dotenv

from funpay_watch.bot import build_router
from funpay_watch.config import Config, load_config
from funpay_watch.fetcher import FunPayClient
from funpay_watch.models import Offer
from funpay_watch.notifier import TelegramNotifier
from funpay_watch.parser import parse_minimum_order
from funpay_watch.poller import Poller
from funpay_watch.single_instance import AlreadyRunning, single_instance
from funpay_watch.storage import Storage
from funpay_watch.watcher import Watcher

log = logging.getLogger("funpay_watch")

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
RETENTION = timedelta(days=7)
HOUSEKEEPING_INTERVAL = timedelta(hours=6)


async def housekeeping(storage: Storage) -> None:
    """Убирает предложения, которых давно нет в выдаче."""
    while True:
        removed = storage.prune(older_than=RETENTION, now=datetime.now(timezone.utc))
        if removed:
            log.info("забыто %d давно пропавших предложений", removed)
        await asyncio.sleep(HOUSEKEEPING_INTERVAL.total_seconds())


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        config = load_config(os.environ)
    except ValueError as exc:
        # Самая частая ошибка первого запуска. Трейсбек тут ничего не объясняет.
        raise SystemExit(f"Ошибка настройки: {exc}\nЗаполните .env по образцу .env.example.")

    # Замок отсекает вторую копию до того, как она успеет разослать что-нибудь
    # по своим порогам. Путь к базе пишем в журнал: если копий всё же окажется
    # две, по этой строке сразу видно, что базы у них разные.
    try:
        with single_instance(config.db_path):
            log.info("база: %s", config.db_path)
            await run(config)
    except AlreadyRunning as exc:
        raise SystemExit(f"Запуск отменён: {exc}")


async def run(config: Config) -> None:
    storage = Storage(config.db_path)
    client = FunPayClient(url=config.chips_url)
    bot = Bot(config.bot_token)

    async def send(text: str) -> int:
        message = await bot.send_message(config.owner_id, text, link_preview_options=NO_PREVIEW)
        return message.message_id

    async def edit(message_id: int, text: str) -> None:
        await bot.edit_message_text(
            chat_id=config.owner_id,
            message_id=message_id,
            text=text,
            link_preview_options=NO_PREVIEW,
        )

    async def minimum_order(offer: Offer) -> Decimal | None:
        response = await client.http.get(offer.url)
        response.raise_for_status()
        return parse_minimum_order(response.content.decode("utf-8"))

    notifier = TelegramNotifier(send=send, edit=edit, fetch_minimum_order=minimum_order)
    poller = Poller(
        fetch_offers=client.fetch_offers, storage=storage, notify=notifier, alert=send
    )
    watcher = Watcher(poller=poller, alert=send, interval=config.poll_interval)

    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(storage, client.fetch_offers, watcher, config.owner_id)
    )

    log.info("служба запущена, опрос раз в %.0f с", config.poll_interval)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.gather(
            dispatcher.start_polling(bot, handle_signals=False),
            watcher.run_forever(),
            housekeeping(storage),
        )
    finally:
        await notifier.drain()
        await client.aclose()
        await bot.session.close()
        storage.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("остановлено вручную")
