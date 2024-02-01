import factory

from trade_engine import models


class StrategyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Strategy
        django_get_or_create = ('name',)

    name = factory.Faker('name')


class EpochFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Epoch

    epoch = 1
    strategy = factory.SubFactory(StrategyFactory)


class PositionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Position
        # django_get_or_create = ('username',)

    # Position(strategy=s, tstamp=SAMPLE_DATA.index[0], asset='aapl', quantity=10, last_price=1)
    quantity = 10
    last_price = 2
    epoch = factory.SubFactory(EpochFactory)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Order

    epoch = factory.SubFactory(EpochFactory)
