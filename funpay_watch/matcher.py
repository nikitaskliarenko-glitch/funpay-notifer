"""Проверка предложения на соответствие порогам."""

from funpay_watch.models import Filters, Offer


def matches(offer: Offer, filters: Filters) -> bool:
    """Проходит ли предложение все заданные пороги."""
    if offer.stock < filters.min_stock:
        return False
    if offer.price_usd > filters.max_price:
        return False
    if offer.reviews < filters.min_reviews:
        return False
    if offer.tenure_months < filters.min_tenure_months:
        return False
    if filters.only_online and not offer.online:
        return False
    if filters.min_stars is not None:
        # Продавец без рейтинга не проходит порог по звёздам: рейтинга нет,
        # а не он равен нулю, и выдавать такого за подходящего нельзя.
        if offer.stars is None or offer.stars < filters.min_stars:
            return False
    return True
