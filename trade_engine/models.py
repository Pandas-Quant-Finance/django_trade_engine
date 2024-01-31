import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Dict, Tuple

import pandas as pd
from django.forms import model_to_dict

from django.db import models
from django.db.models import CheckConstraint
from pytz import UTC

CASH_ASSET = '$$$'
DEFAULT_ASSET_STRATEGY = '-'
DEFAULT_BRACKET_FACTORY = uuid.uuid4
DEFAULT_MAX_DATE = datetime.fromisoformat('9999-12-31').astimezone(UTC)
DEFAULT_MIN_DATE = datetime.fromisoformat('0001-01-01T00:00:00+00:00').astimezone(UTC)


class Strategy(models.Model):

    name = models.CharField(max_length=512)
    start_capital = models.FloatField(default=100_000)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            Position.objects.create(
                strategy=self,
                tstamp=DEFAULT_MIN_DATE,
                asset=CASH_ASSET,
                asset_strategy='cash',
                quantity=self.start_capital,
                last_price=1
            )

    def __str__(self):
        return f'{model_to_dict(self)}'

class Position(models.Model):

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE)
    tstamp = models.DateTimeField()
    asset = models.CharField(max_length=64)
    asset_strategy = models.CharField(max_length=64, default=DEFAULT_ASSET_STRATEGY)
    quantity = models.FloatField()
    last_price = models.FloatField()

    @property
    def value(self):
        return self.quantity * self.last_price

    def weight(self, portfolio_value):
        return self.value / portfolio_value

    def __str__(self):
        return f'{model_to_dict(self)}'

    @staticmethod
    def fetch_most_recent_cash(strategy: Strategy | Iterable = None):
        positions = Position.fetch_most_recent_positions(strategy, asset=CASH_ASSET, include_zero=True)
        assert len(positions) == 1, f"Something happened, expected one position got {len(positions)}\n{positions}"
        return positions[0]

    @staticmethod
    def fetch_most_recent_positions(strategy: Strategy | Iterable = None, asset: str = None, include_zero: bool = False):
        if strategy is not None:
            if not isinstance(strategy, Iterable): strategy = [strategy]
            strategy = [str(s.pk if isinstance(s, Strategy) else s) for s in strategy]

        def get_filter(ns=''):
            filter = f""

            if strategy is not None:
                filter += f" and {ns}strategy_id in ({','.join(strategy)})"
            if asset is not None:
                filter += f" and {ns}asset = '{asset}'"

            return filter

        sql = f"""
            WITH recent as (
                select strategy_id, asset, asset_strategy, max(tstamp) as tstamp
                  from trade_engine_position
                 where 1 = 1 {get_filter()}
                 group by strategy_id, asset_strategy, asset
            ) select pos.*
                from trade_engine_position pos
                join recent on recent.strategy_id = pos.strategy_id
                           and recent.asset = pos.asset
                           and recent.asset_strategy = pos.asset_strategy
                           and recent.tstamp = pos.tstamp
               where 1 = 1 {get_filter('pos.')}
        """

        positions = list(Position.objects.raw(sql))
        return positions if include_zero else filter(lambda p: p.quantity != 0 or p.asset == CASH_ASSET, positions)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['strategy', 'tstamp', 'asset', 'asset_strategy'], name='unique_asset'),
        ]
        indexes = [
            models.Index(fields=['asset', 'tstamp'])
        ]


class Order(models.Model):

    ORDER_TYPES = [
        ('CLOSE', 'CLOSE'),
        ('QUANTITY', 'QUANTITY'),
        ('TARGET_QUANTITY', 'TARGET_QUANTITY'),
        ('PERCENT', 'PERCENT'),
        ('INCREASE_PERCENT', 'INCREASE_PERCENT'),
        ('TARGET_WEIGHT', 'TARGET_WEIGHT'),
    ]

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE)
    asset = models.CharField(max_length=64, null=True, blank=True)
    asset_strategy = models.CharField(max_length=64, default=DEFAULT_ASSET_STRATEGY)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(default=DEFAULT_MAX_DATE, blank=True)
    quantity = models.FloatField(null=True, blank=True)
    limit = models.FloatField(null=True, blank=True)
    stop_limit = models.FloatField(null=True, blank=True)
    stop_limit_activated = models.BooleanField(default=False)
    target_weight_bracket_id = models.CharField(max_length=64, default=DEFAULT_BRACKET_FACTORY, blank=True)
    executed = models.BooleanField(default=False)
    cancelled = models.BooleanField(default=False)
    generated = models.BooleanField(default=False)

    def __str__(self):
        return f'{model_to_dict(self)}'

    class Meta:
        constraints = [
            CheckConstraint(
                check=models.Q(order_type__in=('TARGET_WEIGHT', 'CLOSE')) | ~models.Q(quantity=None),
                name='check_quantity'
            ),
        ]


@dataclass
class Trade:

    # TODO we eventually convert Trade into a model and save it to the database
    #  this is because we later want to be able to switch the orderbook incl trade exectution to a orderbook where we
    #  place the trade as a order at a real broker. then we get a trade execution (one signal more in the chain) from the
    #  broker. we skip this for the moment as we only use it for backtesting right now

    strategy: Strategy  # = models.ForeignKey(Strategy, on_delete=models.CASCADE)
    tstamp: datetime
    asset: str
    quantity: float
    price: float
    asset_strategy: str = DEFAULT_ASSET_STRATEGY
    order: int = None


class Portfolio(object):

    def __init__(self, strategy: Strategy|int):
        self.strategy = strategy.pk if isinstance(strategy, Strategy) else strategy

    @property
    def positions(self) -> Tuple[float, Dict[str, List[Position]]]:
        positions = list(Position.fetch_most_recent_positions(strategy=self.strategy))

        # We need to sum short positions as positive value because the portfolio weights can only sum to exactly 1
        portfolio_value = sum(abs(p.value) for p in positions)

        for p in positions:
            p.weight = p.value / portfolio_value

        return portfolio_value, {
            p.asset: p for p in positions
        }

    def position_history(self, from_index: datetime = DEFAULT_MIN_DATE):
        queries = []
        positions = pd.DataFrame(
            model_to_dict(p) for p in Position.objects\
                .filter(*queries, strategy=self.strategy, tstamp__gte=from_index)\
                .order_by("strategy", "asset", "asset_strategy", "tstamp")\
                .all()
        )

        timeseries = pd.pivot(
            positions,
            values=["quantity", "last_price"],
            index="tstamp",
            columns=["asset", "asset_strategy"]
        ).ffill()

        position_value = pd.concat([timeseries["quantity"] * timeseries["last_price"]], axis=1, keys=["weight"])
        timeseries[("portfolio", "value", None)] = position_value.sum(axis=1)
        weights = (position_value / timeseries[("portfolio", "value")].values)

        return timeseries.join(weights, how="left")
