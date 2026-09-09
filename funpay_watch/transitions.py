"""Решение о том, пора ли писать о предложении."""

from decimal import Decimal

from funpay_watch.models import Offer, OfferState

# Насколько ещё должна упасть цена, чтобы о том же предложении написать снова.
REPEAT_DROP = Decimal("0.05")


def should_notify(previous: OfferState | None, offer: Offer, now_matches: bool) -> bool:
    """Сообщаем в момент перехода предложения в состояние «подходит».

    Один и тот же оффер не повторяется, пока его цена не упадёт ещё
    на REPEAT_DROP от той, о которой уже писали.
    """
    if not now_matches:
        return False
    if previous is None or not previous.matched:
        return True
    if previous.last_notified_price is None:
        return True
    return offer.price_usd <= previous.last_notified_price * (1 - REPEAT_DROP)
