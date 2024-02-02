from datetime import datetime
from datetime import datetime
from typing import Iterable, Callable

import pandas as pd
from django.db import transaction

from trade_engine import models
from trade_engine.strategy.base_strategy import StrategyBase
from trade_engine.strategy.order import Order
from trade_engine.tickers.tick import Tick


class StreamingOrdersStrategy(StrategyBase):

    def __init__(
            self,
            strategy: Callable[[bool, Iterable[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], Iterable[Order] | Order | None],
            strategy_name: str,
            features: pd.DataFrame,
            labels: pd.DataFrame = None,
            weights: pd.DataFrame = None,
            epochs: int = 1
    ):
        super().__init__(strategy_name, epochs)
        self.strategy_order_generator = strategy
        self.features = features
        self.labels = labels
        self.weights = weights

    @transaction.atomic()
    def _on_end_of_bar(
            self,
            strategy: models.Strategy,
            epoch: models.Epoch,
            train_until: datetime,
            ticks: Iterable[Tick],
            date: datetime,
    ):
        # evaluate strategy at t
        features = self.features.loc[:date]
        labels = self.labels.loc[:date] if self.labels is not None else None
        weights = self.weights.loc[:date] if self.weights is not None else None
        is_training_data = features.index[-1] <= train_until.replace(tzinfo=features.index[-1].tzinfo)
        orders = self.on_bar_end(is_training_data, ticks, features, labels, weights)

        # place orders
        if orders is not None:
            tst = max([t.tst for t in ticks])
            for order in orders:
                StrategyBase.place_order(epoch, tst, order)
    def on_bar_end(
            self,
            is_training_data: bool,
            ticks: Iterable[Tick],
            features: pd.DataFrame,
            labels: pd.DataFrame = None,
            weights: pd.DataFrame = None,
    ) -> Iterable[Order] | None:
        # This is where you evaluate the strategy receiving the last tick of a ticker,
        # like the Close price of an EOD ticker. Based on this we hand over feature and label dataframes where you can
        # evaluate your strategy and return the orders to place.
        # TODO we should also send the current orders in case you want to cancel them
        # TODO we should also send a lazy current portfolio

        orders = self.strategy_order_generator(is_training_data, ticks, features, labels, weights)
        if orders is None:
            return None
        elif isinstance(orders, Iterable):
            return orders
        else:
            return [orders]

