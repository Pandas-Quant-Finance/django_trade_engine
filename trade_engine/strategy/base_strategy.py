from abc import abstractmethod
from datetime import datetime
from functools import partial
from pyexpat import model
from typing import List, Iterable, Callable

import pandas as pd
from django.db import transaction

from trade_engine.strategy.order import Order
from trade_engine.tickers.baseticker import BaseTicker
from trade_engine.tickers.tick import Tick
from trade_engine import models


class StrategyBase(object):

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.strategy = models.Strategy(name=strategy_name)
        self.strategy.save()
        self.strategy_id = self.strategy.pk

    def run(self, ticker: BaseTicker):
        # NOTE in case of a "realtime streaming" ticker, this method might never return!

        # TODO we should create the strategy here, we might introduce versioning here and an option to delete
        #  an eventually already existing strategy

        # init
        self.on_init(self.strategy)

        # TODO we introduce a new "Epoch" object where we loop trough

        # start backtest ticker
        if handler := self.on_end_of_bar_event_handler():
            ticker.start(self.strategy_id, partial(handler, self.strategy))
        else:
            ticker.start(self.strategy_id)

        # end run
        self.on_epoch_end()

    @transaction.atomic()
    def on_init(self, strategy: models.Strategy):
        pass

    @abstractmethod
    def on_end_of_bar_event_handler(self) -> Callable[[models.Strategy, Iterable[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], None] | None:
        pass

    def on_epoch_end(self):
        pass

    @staticmethod
    def place_order(strategy: models.Strategy, valid_from: datetime, order: Order):
        models.Order(**{
            "strategy": strategy,
            "valid_from": valid_from,
            **order.to_dict()
        }).save()
