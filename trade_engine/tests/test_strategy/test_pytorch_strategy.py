from datetime import datetime

import numpy as np
import pandas as pd
from django.test import SimpleTestCase, TestCase

from trade_engine import models
from trade_engine.strategy.ml_strategy import PyTorchModelStrategy
from trade_engine.strategy.order import Order
from trade_engine.strategy.streaming_orders_strategy import StreamingOrdersStrategy
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tickers.replayticker import PandasReplayTicker


df = SAMPLE_DATA["aapl"]


# TODO 2 implement a test using a pytorch model and train/test data and hyper parameters

#class TestStreamingOrderStrategy(SimpleTestCase):
class TestStreamingOrderStrategy(TestCase):
    databases = ["default"]

    def test_sma_strategy(self):
        import torch
        from torch import nn

        # calculate signals
        fast = df["Close"].rolling(20).mean()
        slow = df["Close"].rolling(60).mean()
        signal = fast / slow - 1

        class TestModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.nn = nn.Sequential(
                    nn.Linear(10, 5),
                    nn.Tanh(),
                    nn.Linear(5, 1),
                    nn.Sigmoid(),
                )

            def forward(self, x):
                # Note that x will always be a pandas dataframe
                if len(x) < 10: return None
                return self.nn(torch.from_numpy(x[-10:].astype('float32').values.reshape((1, -1))))

        class MyLoss(torch.nn.Module):
            
            def __init__(self):
                super().__init__()
                self.loss = torch.nn.MSELoss()

            def forward(self, x, labels):
                # Note that x, labels will always be a pandas dataframes
                if len(x) < 1: return None
                return self.loss(x, torch.from_numpy(labels[-1:].astype('float32').values.reshape((1, -1))))

        # create strategy
        strategy = PyTorchModelStrategy(
            strategy_name='test_streaming_order_strategy',
            model=TestModel(),
            optimizer=torch.optim.Adam,
            loss=MyLoss(),
            features=signal.to_frame(),
            labels=df["Close"].pct_change().shift(-1).to_frame(),
            epochs=2,
        )

        # backtest strategy
        strategy.run(PandasReplayTicker({"aapl": df}), train_until=datetime.fromisoformat('2021-09-16T00:00:00+00:00'),)
        timeseries = models.Portfolio(strategy.strategy).position_history()
        print(timeseries.columns)
        print(timeseries)
        self.assertAlmostEquals(
            np.sum(timeseries[("portfolio", "value")].tail(1).values / timeseries[("portfolio", "value")].head(1).values),
            1.5839,
            4
        )

        self.assertEqual(models.Order.objects.count(), 13 * 2)  # later we test 2 epochs



