"""Типы данных предметной области."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Offer:
    """Одно предложение из общего списка.

    Ключ `offer_id` устойчив: он собран из идентификаторов продавца, игры,
    раздела и способа передачи, поэтому переживает изменения цены и наличия.
    """

    offer_id: str
    seller_id: int
    seller_name: str
    stars: int | None
    reviews: int
    tenure_months: int
    # Исходная формулировка стажа для показа в сообщении: в месяцах «на сайте
    # 3 недели» схлопывается в ноль, а читателю нужна фраза целиком.
    tenure_text: str
    stock: int
    price_usd: Decimal
    online: bool
    method: str
    url: str


@dataclass(frozen=True, slots=True)
class Filters:
    """Пороги отбора. Только критерии совпадения, без состояния поиска.

    `min_stars` равный None означает, что рейтинг не проверяется вовсе.
    """

    min_stock: int
    min_stars: int | None
    min_reviews: int
    max_price: Decimal
    min_tenure_months: int
    only_online: bool


@dataclass(frozen=True, slots=True)
class OfferState:
    """Что мы помним о предложении с прошлого цикла.

    `last_notified_price` хранит цену, о которой уже сообщали, чтобы повторно
    писать только при заметном дальнейшем снижении.
    """

    offer_id: str
    price_usd: Decimal
    stock: int
    matched: bool
    last_notified_price: Decimal | None
