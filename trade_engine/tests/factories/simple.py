import factory

from trade_engine import models


class StrategyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Strategy
        django_get_or_create = ('name',)

    name = factory.Faker('name')


class PositionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Position
        # django_get_or_create = ('username',)

    # Position(strategy=s, tstamp=SAMPLE_DATA.index[0], asset='aapl', quantity=10, last_price=1)
    quantity = 10
    last_price = 2
    strategy = factory.SubFactory(StrategyFactory)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Order

    strategy = factory.SubFactory(StrategyFactory)
