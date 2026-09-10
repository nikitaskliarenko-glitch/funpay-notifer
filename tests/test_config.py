import pathlib

import pytest

from funpay_watch.config import Config, load_config

MINIMAL = {"BOT_TOKEN": "123:abc", "OWNER_ID": "777"}


def test_reads_the_two_required_settings():
    config = load_config(MINIMAL)

    assert config.bot_token == "123:abc"
    assert config.owner_id == 777


def test_falls_back_to_documented_defaults():
    config = load_config(MINIMAL)

    assert config.chips_url == "https://funpay.com/chips/99/"
    assert config.poll_interval == 30.0
    assert str(config.db_path).endswith("funpay_watch.db")


def test_settings_can_be_overridden():
    config = load_config({**MINIMAL, "POLL_INTERVAL": "45", "DB_PATH": "/data/x.db"})

    assert config.poll_interval == 45.0
    assert config.db_path == pathlib.Path("/data/x.db").resolve()


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "OWNER_ID"])
def test_missing_required_setting_is_reported_by_name(missing):
    env = {k: v for k, v in MINIMAL.items() if k != missing}

    with pytest.raises(ValueError, match=missing):
        load_config(env)


def test_owner_id_must_be_a_number():
    with pytest.raises(ValueError, match="OWNER_ID"):
        load_config({**MINIMAL, "OWNER_ID": "меня"})


def test_relative_database_path_is_resolved_to_an_absolute_one():
    """Относительный путь создаёт базу там, откуда запущен процесс.

    Две копии, запущенные из разных папок, получали бы разные базы: одна
    отвечала бы на команды, другая рассылала бы уведомления по умолчаниям.
    """
    config = load_config({**MINIMAL, "DB_PATH": "funpay_watch.db"})

    assert config.db_path.is_absolute()
    assert config.db_path.name == "funpay_watch.db"


def test_default_database_path_is_absolute_too():
    assert load_config(MINIMAL).db_path.is_absolute()
