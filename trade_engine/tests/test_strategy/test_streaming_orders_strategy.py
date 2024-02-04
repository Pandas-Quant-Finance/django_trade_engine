
import numpy as np
import pandas as pd
from django.test import SimpleTestCase, TestCase

from trade_engine import models
from trade_engine.strategy.order import Order
from trade_engine.strategy.streaming_orders_strategy import StreamingOrdersStrategy
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tickers.replayticker import PandasReplayTicker


df = SAMPLE_DATA["aapl"]


# TODO 2 implement a test using a pytorch model and train/test data and hyper parameters

#class TestStreamingOrderStrategy(SimpleTestCase):
class TestStreamingOrderStrategy(TestCase):
    databases = ["default"]

    def test_streaming_sma_strategy(self):
        # calculate signals
        fast = df["Close"].rolling(20).mean()
        slow = df["Close"].rolling(60).mean()
        signal = fast > slow
        buy = ((signal) & (~signal).shift(1)).rename("buy")
        sell = ((~signal) & (signal).shift(1)).rename("sell")

        def strategy(epoch, bool, ticks, features, *args):
            # create orders from signals
            if features["buy"].iloc[-1]:
                return Order(asset='aapl', order_type='PERCENT', quantity=1.0)
            elif features["sell"].iloc[-1]:
                return Order(asset='aapl', order_type='CLOSE')
            else:
                return None

        # create strategy
        strategy = StreamingOrdersStrategy(
            strategy=strategy,
            strategy_name='test_streaming_order_strategy',
            features=pd.concat([buy, sell], axis=1),
            epochs=2,
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

        self.assertEqual(models.Order.objects.count(), 13 * 2)  # later we test 2 epochs



