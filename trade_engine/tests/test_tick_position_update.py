from django.dispatch import receiver
from django.test import TestCase

from trade_engine.models import Position
from trade_engine.signals import tick
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tests.factories.simple import PositionFactory
from trade_engine.tickers.replayticker import PandasReplayTicker


class TestTickPosition(TestCase):

    def test_pandas_ticker(self):
        @receiver(tick)
        def update_portfolio_after_tick(sender, signal, ticks):
            print(sender, ticks)

        PositionFactory.create(tstamp=SAMPLE_DATA.index[0], asset='aapl')
        PandasReplayTicker(SAMPLE_DATA.tail()).start()
        print(list(Position.objects.all()))

        self.assertEqual(len(list(Position.objects.all())), 5 + 1 + 1)
        prices = [p.last_price for p in Position.objects.filter(asset='aapl', tstamp__gt=SAMPLE_DATA.index[0]).order_by('tstamp')]
        self.assertEqual(SAMPLE_DATA.tail()[('aapl', 'Close')].tolist(), prices)
