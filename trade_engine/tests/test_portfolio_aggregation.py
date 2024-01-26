from django.test import TestCase

from trade_engine.models import Portfolio
from trade_engine.tests.data import SAMPLE_DATA
from trade_engine.tests.factories.simple import PositionFactory, StrategyFactory


class TestPortfolioAggregation(TestCase):

    def test_pandas_ticker(self):
        s = StrategyFactory(start_capital=9000)
        PositionFactory.create(strategy=s, tstamp=SAMPLE_DATA.index[0], asset='aapl', last_price=100)
        PositionFactory.create(strategy=s, tstamp=SAMPLE_DATA.index[0], asset='msft', last_price=100, quantity=-3)
        PositionFactory.create(strategy=s, tstamp=SAMPLE_DATA.index[0], asset='tlt', last_price=50, quantity=4)

        pv, positions = Portfolio(s).positions
        for _, p in positions.items():
            print(p.asset, p.quantity, p.last_price, '\t', p.value, '\t', p.weight)

        self.assertAlmostEquals(sum(map(lambda x: abs(x.weight), positions.values())), 1.0)

