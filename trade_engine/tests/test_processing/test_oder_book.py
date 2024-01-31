from datetime import datetime
from typing import List

import pandas as pd
from django.dispatch import receiver
from django.test import TestCase
from parameterized import parameterized

from trade_engine.processing.orderbook import new_orderbook
from trade_engine.signals import trade_executed
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tests.factories.simple import OrderFactory, PositionFactory, StrategyFactory
from trade_engine.tickers.replayticker import PandasReplayTicker
from trade_engine import models
from trade_engine.tickers.tick import Tick

df = SAMPLE_DATA.tail()


# FIXME high low sonder tick muss vor dem close kommen, darf im orderbook aber nur bei der Limit Prüfung verwendet werden


class TestTickOrderExecution(TestCase):

    @parameterized.expand([
        ('TARGET_WEIGHT', ['FOO', 'BAR'], 0.5, 100_000 * 0.5 / 10),
        ('CLOSE', ['BAR'], None, -40000.0),
        ('QUANTITY', ['FOO'], 3, 3),
        ('TARGET_QUANTITY', ['BAR'], 40007, 7.0),
        ('PERCENT', ['FOO'], 0.5, 100_000 * 0.5 / 10),
        ('INCREASE_PERCENT', ['BAR'], 0.5, 60000 * 0.5),
    ])
    def test_order_types(self, order_type, assets, quantity, expected_quantity):

        @receiver(trade_executed)
        def update_portfolio_after_trade(sender, signal, trades: List[models.Trade], **kwargs):
            print(trades)
            self.assertIn(trades[0].asset, assets)
            self.assertEqual(1, len(trades))
            self.assertEqual(trades[0].quantity, expected_quantity)

        s = StrategyFactory.create()
        pos = PositionFactory.create(strategy=s, tstamp=datetime(2019, 12, 31), asset='BAR', quantity=40000)
        OrderFactory.create(strategy=s, asset='FAKE', order_type=order_type, quantity=99, valid_from=datetime(2020, 1, 1))
        for a in assets:
            OrderFactory.create(strategy=s, asset=a, order_type=order_type, quantity=quantity, valid_from=datetime(2020, 1, 1), target_weight_bracket_id=str(assets))

        print(models.Order.objects.all())

        new_orderbook(*[
            Tick(
                strategy_id=s.pk,
                asset=a,
                tst=datetime(2020, 1, 2),
                bid=10,
                ask=10,
            ) for a in assets
        ], stop_propagation=True)

    def test_limit(self):
        pass

    def test_stop_limit(self):
        pass
