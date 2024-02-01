from django.test import TestCase
from parameterized import parameterized

from trade_engine import models
from trade_engine.signals import trade_executed
from trade_engine.tests.factories.simple import EpochFactory


class TestTradeExecution(TestCase):

    @parameterized.expand([
        (1, -1, -100, 10, 0),
        (-3, 2, 300, -20 + 100, -1),
        (-3, 6, 300, 300 - 660, 3),
    ])
    def test_long_short_swing(self, q1, q2, v1, v2, exp_qty):
        e = EpochFactory.create()

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-01', asset='abc', price=100, quantity=q1, epoch=e)])
        self.assertEqual(len(list(models.Position.objects.all())), 3)
        self.assertEqual(models.Position.fetch_most_recent_cash(e).value, e.strategy.start_capital + v1)

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-02', asset='abc', price=110, quantity=q2, epoch=e)])
        all = {p.asset: p for p in models.Position.objects.all()}
        self.assertEqual(len(all), 2)
        self.assertEqual(models.Position.fetch_most_recent_cash(e).value, e.strategy.start_capital + v2)
        self.assertEqual(all['abc'].quantity, exp_qty)

