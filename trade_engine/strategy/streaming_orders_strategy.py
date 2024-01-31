from abc import abstractmethod
from typing import List, Iterable, Callable

import pandas as pd
from django.db import transaction

from trade_engine import models
from trade_engine.strategy.base_strategy import StrategyBase
from trade_engine.strategy.order import Order
from trade_engine.tickers.tick import Tick


class StreamingOrdersStrategy(StrategyBase):

    def __init__(self):
        super().__init__()

    def on_end_of_bar_event_handler(self) -> Callable[[models.Strategy, Iterable[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], None] | None:
        return self._on_end_of_bar

    @transaction.atomic()
    def _on_end_of_bar(self, strategy: models.Strategy, ticks: Iterable[Tick], features: pd.DataFrame, labels: pd.DataFrame = None, weights: pd.DataFrame = None):
        # evaluate strategy at t
        orders = self.on_tick(ticks, features, labels, weights)

        # place orders
        tst = max([t.tst for t in ticks])
        for order in orders:
            StrategyBase.place_order(strategy, tst, orders)

    @abstractmethod
    def on_tick(self, tick: Iterable[Tick], features: pd.DataFrame, labels: pd.DataFrame = None, weights: pd.DataFrame = None) -> Iterable[Order]:
        # This is where you evaluate the strategy receiving the last tick of a ticker,
        # like the Close price of an EOD ticker. Based on this we hand over feature and label dataframes where you can
        # evaluate your strategy and return the orders to place.
        # TODO we should pass an easy to use order factory
        # TODO we should also send the current orders in case you want to cancel them
        # TODO we should also send a lazy current portfolio
        pass
