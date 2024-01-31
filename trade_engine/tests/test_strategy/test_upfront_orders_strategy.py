import pandas as pd
from django.dispatch import receiver
from django.test import TestCase
from parameterized import parameterized

from trade_engine.signals import trade_executed
from trade_engine.strategy.order import Order
from trade_engine.strategy.upfront_orders_strategy import UpfrontOrdersStrategy
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tests.factories.simple import OrderFactory, PositionFactory, StrategyFactory
from trade_engine.tickers.replayticker import PandasReplayTicker
from trade_engine import models


df = SAMPLE_DATA["aapl"]


class TestUpfrontOrderStrategy(TestCase):

    # TODO make the same test where we pass the rolling means as features into a streaming strategy
    def test_sma_strategy(self):
        # calculate sma
        fast = df["Close"].rolling(20).mean()
        slow = df["Close"].rolling(60).mean()
        signal = fast > slow
        buy = (signal) & (~signal).shift(-1)
        sell = (~signal) & (signal).shift(-1)

        buys = buy.apply(lambda signal: Order(asset='aapl', order_type='PERCENT', quantity=1.0) if signal else None)
        sells = sell.apply(lambda signal: Order(asset='aapl', order_type='CLOSE') if signal else None)

        # create orders # TODO provide order factory from the strategy object
        strategy = UpfrontOrdersStrategy(
            strategy_name='test_strategy',
            orders=buys.combine_first(sells),
        )

        strategy.run(PandasReplayTicker({"aapl": df}))
        print(models.Portfolio(strategy.strategy).position_history())


