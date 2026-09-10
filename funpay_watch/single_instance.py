"""Замок, не дающий запустить вторую копию бота на той же базе.

Две копии на одной базе шлют дубли, а две копии на разных базах ведут себя
куда хуже: команды достаются одной, а рассылку ведёт другая со своими
порогами. Снаружи это выглядит так, будто фильтры не работают.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:  # POSIX
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt


class AlreadyRunning(RuntimeError):
    """На этой базе уже работает другая копия бота."""


def _try_lock(handle) -> bool:
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock(handle) -> None:
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextmanager
def single_instance(db_path: str | Path) -> Iterator[Path]:
    """Держит замок рядом с базой на всё время работы.

    Замок привязан именно к базе, а не к машине: разные базы друг другу
    не мешают, что удобно для запуска боевой и пробной копий бок о бок.
    """
    lock_path = Path(db_path).with_suffix(Path(db_path).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0)
        if not _try_lock(handle):
            raise AlreadyRunning(
                f"бот уже запущен на базе {Path(db_path).resolve()}."
                " Вторая копия рассылала бы уведомления по своим порогам."
                " Остановите лишнюю: systemctl stop funpay-watch"
            )
        handle.truncate(0)
        handle.write(str(os.getpid()).encode())
        handle.flush()
        yield lock_path
    finally:
        _unlock(handle)
        handle.close()
