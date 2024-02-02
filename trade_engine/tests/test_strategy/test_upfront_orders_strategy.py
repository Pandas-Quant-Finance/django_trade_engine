import numpy as np
from django.test import SimpleTestCase, TestCase

from trade_engine import models
from trade_engine.strategy.order import Order
from trade_engine.strategy.upfront_orders_strategy import UpfrontOrdersStrategy
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tickers.replayticker import PandasReplayTicker

df = SAMPLE_DATA["aapl"]


#class TestUpfrontOrderStrategy(SimpleTestCase):
class TestUpfrontOrderStrategy(TestCase):
    databases = ["default"]

    def test_sma_strategy(self):
        # calculate signals
        fast = df["Close"].rolling(20).mean()
        slow = df["Close"].rolling(60).mean()
        signal = fast > slow
        buy = (signal) & (~signal).shift(1)
        sell = (~signal) & (signal).shift(1)

        # create orders from signals
        buys = buy.apply(lambda signal: Order(asset='aapl', order_type='PERCENT', quantity=1.0) if signal else None)
        sells = sell.apply(lambda signal: Order(asset='aapl', order_type='CLOSE') if signal else None)

        # create strategy
        strategy = UpfrontOrdersStrategy(
            strategy_name='test_upfront_order_strategy',
            orders=buys.combine_first(sells),
        )

        # backtest strategy
        strategy.run(PandasReplayTicker({"aapl": df}))
        timeseries = models.Portfolio(strategy.strategy).position_history()
        print(timeseries.columns)
        print(timeseries)

        self.assertAlmostEquals(
            np.sum(timeseries[("portfolio", "value")].tail(1).values / timeseries[("portfolio", "value")].head(1).values),
            1.5839,
            4
        )

        self.assertEqual(models.Order.objects.count(), 13)


