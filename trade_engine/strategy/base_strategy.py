from datetime import datetime
from functools import partial

from django.db import transaction

from trade_engine import models
from trade_engine.strategy.order import Order
from trade_engine.tickers.baseticker import BaseTicker


class StrategyBase(object):

    def __init__(self, strategy_name: str, epochs: int = 1):
        self.strategy_name = strategy_name
        self.epochs = epochs
        self.strategy = None

    def run(self, ticker: BaseTicker, **strategy_kwargs):
        # NOTE in case of a "realtime streaming" ticker, this method might never return!

        # initialize strategy: we might introduce versioning here and an option to delete an eventually already
        # existing strategy
        self.strategy = models.Strategy(name=self.strategy_name, **strategy_kwargs)
        self.strategy.save()

        # we introduce a new "Epoch" object where we loop trough
        for e in range(self.epochs):
            # create a new default epoch
            epoch = models.Epoch(strategy=self.strategy, epoch=e)
            epoch.save()

            if e <= 0:
                # init
                self.on_init(epoch)

            # start backtest ticker
            if hasattr(self, "_on_end_of_bar"):
                ticker.start(
                    epoch.pk,
                    partial(self._on_end_of_bar, self.strategy, epoch, self.strategy.train_until)
                )
            else:
                ticker.start(epoch.pk)

            # end run
            self.on_epoch_end()

    @transaction.atomic()
    def on_init(self, epoch: models.Epoch):
        pass

    def on_epoch_end(self):
        pass

    @staticmethod
    def place_order(epoch: models.Epoch, valid_from: datetime, order: Order):
        try:
            models.Order(**{
                "epoch": epoch,
                "valid_from": valid_from,
                **order.to_dict()
            }).save()
        except Exception as e:
            raise e