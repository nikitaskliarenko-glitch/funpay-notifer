from decimal import Decimal

from funpay_watch.notifier import TelegramNotifier

from tests.test_matcher import make_offer


class Chat:
    def __init__(self):
        self.sent = []
        self.edits = []

    async def send(self, text):
        self.sent.append(text)
        return len(self.sent)

    async def edit(self, message_id, text):
        self.edits.append((message_id, text))


async def test_sends_the_formatted_offer():
    chat = Chat()
    notifier = TelegramNotifier(send=chat.send, edit=chat.edit)

    await notifier(make_offer(price_usd=Decimal("0.0065")))
    await notifier.drain()

    assert chat.sent[0].startswith("Robux $0.0065 за 1 шт.")
    assert chat.edits == []


async def test_minimum_order_is_added_by_editing_the_sent_message():
    chat = Chat()

    async def lookup(offer):
        return Decimal("2500")

    notifier = TelegramNotifier(send=chat.send, edit=chat.edit, fetch_minimum_order=lookup)

    await notifier(make_offer())
    await notifier.drain()

    assert len(chat.sent) == 1
    assert chat.edits[0][0] == 1
    assert "Минимальный заказ: 2500 ед." in chat.edits[0][1]


async def test_message_goes_out_before_the_minimum_order_is_looked_up():
    """Скорость важнее полноты: справка догоняет уже отправленное сообщение."""
    chat = Chat()
    order = []

    async def lookup(offer):
        order.append("lookup")
        return Decimal("2")

    async def send(text):
        order.append("send")
        return 1

    notifier = TelegramNotifier(send=send, edit=chat.edit, fetch_minimum_order=lookup)

    await notifier(make_offer())
    await notifier.drain()

    assert order == ["send", "lookup"]


async def test_unreadable_minimum_order_leaves_the_message_as_sent():
    chat = Chat()

    async def lookup(offer):
        raise RuntimeError("страница предложения недоступна")

    notifier = TelegramNotifier(send=chat.send, edit=chat.edit, fetch_minimum_order=lookup)

    await notifier(make_offer())
    await notifier.drain()

    assert len(chat.sent) == 1
    assert chat.edits == []


async def test_offer_without_a_minimum_order_is_not_edited():
    chat = Chat()

    async def lookup(offer):
        return None

    notifier = TelegramNotifier(send=chat.send, edit=chat.edit, fetch_minimum_order=lookup)

    await notifier(make_offer())
    await notifier.drain()

    assert chat.edits == []
