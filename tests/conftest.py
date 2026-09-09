import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def row():
    """Отдаёт одну сохранённую строку предложения по имени фикстуры."""

    def _load(name: str) -> str:
        return (FIXTURES / "rows" / f"{name}.html").read_text(encoding="utf-8")

    return _load


@pytest.fixture
def live_page() -> str:
    """Снимок живой страницы https://funpay.com/chips/99/ с ценами в долларах."""
    return (FIXTURES / "chips99.html").read_text(encoding="utf-8")
