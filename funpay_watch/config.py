"""Настройки службы из переменных окружения."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from funpay_watch.fetcher import CHIPS_URL


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    owner_id: int
    db_path: Path
    chips_url: str
    poll_interval: float


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"не задана переменная окружения {name}")
    return value


def load_config(env: Mapping[str, str]) -> Config:
    """Собирает настройки, называя недостающую переменную по имени."""
    token = _required(env, "BOT_TOKEN")
    raw_owner = _required(env, "OWNER_ID")
    try:
        owner_id = int(raw_owner)
    except ValueError:
        raise ValueError(f"OWNER_ID должен быть числом, а не {raw_owner!r}") from None

    return Config(
        bot_token=token,
        owner_id=owner_id,
        # Путь разворачиваем в абсолютный сразу. Относительный создавал бы
        # базу там, откуда запущен процесс, и две копии из разных папок
        # разошлись бы по разным базам: одна отвечает на команды, другая
        # рассылает уведомления по умолчаниям, будто фильтры не работают.
        db_path=Path(env.get("DB_PATH") or "funpay_watch.db").resolve(),
        chips_url=env.get("CHIPS_URL") or CHIPS_URL,
        poll_interval=float(env.get("POLL_INTERVAL") or 30.0),
    )
