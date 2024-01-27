import pandas as pd
from django.dispatch import receiver
from django.test import TestCase
from parameterized import parameterized

from trade_engine.signals import trade_executed
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tests.factories.simple import OrderFactory, PositionFactory, StrategyFactory
from trade_engine.tickers.replayticker import PandasReplayTicker
from trade_engine import models


df = SAMPLE_DATA.tail()

# FIXME high low sonder tick muss vor dem close kommen, darf im orderbook aber nur bei der Limit Prüfung verwendet werden


class TestTickOrderExecution(TestCase):

    def test_target_weight(self):
        s = StrategyFactory.create()
        PositionFactory.create(strategy=s, tstamp=df.index[0], asset='aapl', quantity=10)
        print(models.Portfolio(s).positions)

        OrderFactory.create(
            strategy=s,
            order_type='TARGET_WEIGHT',
            valid_from=df.index[0],
            target_weights={'aapl': 0.5, 'msft': 0.5},
        )

        OrderFactory.create(
            strategy=s,
            order_type='TARGET_WEIGHT',
            valid_from=df.index[1],
            target_weights={'aapl': 0.7, 'msft': 0.3},
        )

        OrderFactory.create(
            strategy=s,
            order_type='TARGET_WEIGHT',
            valid_from=df.index[2],
            target_weights={'aapl': 1.0},
        )

        print(models.Order.objects.first())

        # place orders here
        # change target weights OrderFactory.create(strategy=s, order_type='TARGET_WEIGHT', valid_from=df.index[1], target_weights={''})
        PandasReplayTicker(df).start()
        print(models.Portfolio(s).positions)
        print(models.Position.objects.all())

        timeseries = models.Portfolio(s).position_history()
        weights = timeseries["weight"]
        print(weights)

        # assert weighs equal to 1
        pd.testing.assert_series_equal(weights.sum(axis=1), pd.Series(1.0, index=weights.index), check_names=False)

        # assert weights to be close to expected weights
        pd.testing.assert_series_equal(weights[("aapl", "-")].round(decimals=2), pd.Series([None, 0.02, 0.5, 0.7, 1.0, 1.0], index=weights.index), check_names=False)
        pd.testing.assert_series_equal(weights[("msft", "-")].round(decimals=2), pd.Series([None, None, 0.5, 0.3, 0.0, 0.0], index=weights.index), check_names=False)

    def test_target_weights_with_shorts(self):
        # TODO add a test with shorts
        pass

    @parameterized.expand([
        ('CLOSE', 0, 10),
        ('QUANTITY', 10, 10),
        ('QUANTITY', -10, -10),
        ('TARGET_QUANTITY', 5, -5),
        ('TARGET_QUANTITY', 15, 5),
        ('PERCENT', 0.5, 100_000 * 0.5 / df[('aapl', 'Open')].iloc[2]),
    ])
    def test_order_types(self, order_type, quantity, expected_quantity):

        @receiver(trade_executed)
        def trade_execution(sender, signal, trades, **kwargs):
            t = trades[0]
            models.Position.objects.filter(strategy=t.strategy, asset=t.asset, asset_strategy=t.asset_strategy).first()
            self.assertEqual(t.quantity, expected_quantity)

            print(sender, trades)

        s = StrategyFactory.create()
        print(s.name, order_type)
        PositionFactory.create(strategy=s, tstamp=df.index[0], asset='aapl', quantity=10)

        # place orders here
        OrderFactory.create(strategy=s, asset='aapl', order_type=order_type, valid_from=df.index[1], valid_until=df.index[-2], quantity=quantity)
        PandasReplayTicker(df).start()

#    def test_order_limits(self):
#        df = SAMPLE_DATA.tail()
#        df.to_csv("debugging.csv")
