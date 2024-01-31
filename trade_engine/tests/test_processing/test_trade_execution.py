from django.test import TestCase

from trade_engine import models
from trade_engine.signals import trade_executed
from trade_engine.tests.factories.simple import StrategyFactory


class TestTradeExecution(TestCase):

    def test_long(self):
        s = StrategyFactory.create()

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-01', asset='abc', price=100, quantity=1, strategy=s)])
        self.assertEqual(len(list(models.Position.objects.all())), 3)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital - 100)

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-02', asset='abc', price=110, quantity=-1, strategy=s)])
        all = {p.asset: p for p in models.Position.objects.all()}
        self.assertEqual(len(all), 2)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital + 10)
        self.assertEqual(all['abc'].quantity, 0)

    def test_short(self):
        s = StrategyFactory.create()

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-01', asset='abc', price=100, quantity=-3, strategy=s)])
        self.assertEqual(len(list(models.Position.objects.all())), 3)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital + 300)

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-02', asset='abc', price=110, quantity=2, strategy=s)])
        all = {p.asset: p for p in models.Position.objects.all()}
        self.assertEqual(len(all), 2)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital - 20 + 100)
        self.assertEqual(all['abc'].quantity, -1)

    def test_swing(self):
        s = StrategyFactory.create()

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-01', asset='abc', price=100, quantity=-3, strategy=s)])
        self.assertEqual(len(list(models.Position.objects.all())), 3)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital + 300)

        trade_executed.send(sender=self.__class__, trades=[models.Trade(tstamp='2020-01-02', asset='abc', price=110, quantity=6, strategy=s)])
        all = {p.asset: p for p in models.Position.objects.all()}
        self.assertEqual(len(all), 2)
        self.assertEqual(models.Position.fetch_most_recent_cash(s).value, s.start_capital + 300 - 660)
        self.assertEqual(all['abc'].quantity, 3)
        self.assertEqual(all['abc'].value, 330)
