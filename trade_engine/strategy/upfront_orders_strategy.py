from abc import abstractmethod
from typing import List, Iterable, Callable

import pandas as pd

from trade_engine.strategy.base_strategy import StrategyBase
from trade_engine.tickers.baseticker import BaseTicker
from trade_engine.tickers.tick import Tick
from trade_engine import models
from trade_engine.strategy.order import Order


class UpfrontOrdersStrategy(StrategyBase):

    def __init__(
            self,
            strategy_name: str,
            orders: "pd.Series[Order]",
    ):
        super().__init__(strategy_name, epochs=1)
        self.orders = orders[~pd.isnull(orders)]

    def on_init(self, epoch: models.Epoch):
        # place all orders upfont
        for idx, order in self.orders.items():
            StrategyBase.place_order(epoch, idx, order)

    def on_end_of_bar_event_handler(self) -> Callable[[models.Epoch, Iterable[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], None] | None:
        return None
