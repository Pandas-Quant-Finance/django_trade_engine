from typing import List

from django.apps import AppConfig
from django.dispatch import receiver

from .signals import tick, position_updated, trade_executed
from .tickers.tick import Tick


class TradeEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trade_engine'


# subscribe for signals
# BaseTicker.tick() -> update portfolio -> process order book (execute order) -> update portfolio

@receiver(tick)
def update_positions_after_tick(sender, signal, ticks: List[Tick], **kwargs):
    from .processing.portfolio import position_roll_forward

    position_roll_forward(*ticks)
    position_updated.send(sender=sender, ticks=ticks)


@receiver(position_updated)
def process_order_book(sender,  signal, ticks: List[Tick], **kwargs):
    from .processing.orderbook import new_orderbook

    new_orderbook(*ticks)


@receiver(trade_executed)
def update_portfolio_after_trade(sender, signal, trades: List['trade_engine.models'], **kwargs):
    from .processing.portfolio import position_update
    from .processing.trades import save_trades

    save_trades(*trades, silent=True)
    position_update(*trades)
