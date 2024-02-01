import uuid
from datetime import datetime
from typing import Iterable, List, Dict, Tuple

import pandas as pd
from django.db import models
from django.db.models import CheckConstraint
from django.forms import model_to_dict
from pytz import UTC

CASH_ASSET = '$$$'
DEFAULT_ASSET_STRATEGY = '-'
DEFAULT_BRACKET_FACTORY = uuid.uuid4
DEFAULT_MAX_DATE = datetime.fromisoformat('9999-12-31').astimezone(UTC)
DEFAULT_MIN_DATE = datetime.fromisoformat('0001-01-01T00:00:00+00:00').astimezone(UTC)


class Strategy(models.Model):

    name = models.CharField(max_length=512)
    start_capital = models.FloatField(default=100_000)
    train_until = models.DateTimeField(default=DEFAULT_MAX_DATE)
    hyper_parameters = models.JSONField(null=True, blank=True)

    def last_epoch(self) -> 'Epoch':
        return (list(self.epochs.all().order_by("epoch")) or [None])[-1]

    def __str__(self):
        return f'{model_to_dict(self)}'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_strategy'),
        ]


class Epoch(models.Model):

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='epochs')
    epoch = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            Position.objects.create(
                epoch=self,
                tstamp=DEFAULT_MIN_DATE,
                asset=CASH_ASSET,
                asset_strategy='cash',
                quantity=self.strategy.start_capital,
                last_price=1
            )


class Position(models.Model):

    epoch = models.ForeignKey(Epoch, on_delete=models.CASCADE)
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
    def fetch_most_recent_cash(epoch: Epoch | Iterable[Epoch] = None):
        positions = Position.fetch_most_recent_positions(epoch, asset=CASH_ASSET, include_zero=True)
        assert len(positions) == 1, f"Something happened, expected one position got {len(positions)}\n{positions}"
        return positions[0]

    @staticmethod
    def fetch_most_recent_positions(epoch: Epoch | Iterable[Epoch] = None, asset: str = None, include_zero: bool = False):
        if epoch is not None:
            if not isinstance(epoch, Iterable): epoch = [epoch]
            epoch = [str(e.pk if isinstance(e, Epoch) else e) for e in epoch]

        def get_filter(ns=''):
            filter = f""

            if epoch is not None:
                filter += f" and {ns}epoch_id in ({','.join(epoch)})"
            if asset is not None:
                filter += f" and {ns}asset = '{asset}'"

            return filter

        sql = f"""
            WITH recent as (
                select epoch_id, asset, asset_strategy, max(tstamp) as tstamp
                  from trade_engine_position
                 where 1 = 1 {get_filter()}
                 group by epoch_id, asset_strategy, asset
            ) select pos.*
                from trade_engine_position pos
                join recent on recent.epoch_id = pos.epoch_id
                           and recent.asset = pos.asset
                           and recent.asset_strategy = pos.asset_strategy
                           and recent.tstamp = pos.tstamp
               where 1 = 1 {get_filter('pos.')}
        """

        positions = list(Position.objects.raw(sql))
        return positions if include_zero else filter(lambda p: p.quantity != 0 or p.asset == CASH_ASSET, positions)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['epoch', 'asset', 'asset_strategy', 'tstamp'], name='unique_asset_position'),
        ]
        indexes = [
            # models.Index(fields=['strategy', 'asset', 'asset_strategy', 'tstamp']),  # is already a constraint
            models.Index(fields=['epoch', 'asset', 'tstamp']),
            models.Index(fields=['epoch', 'asset']),
        ]


class Order(models.Model):

    ORDER_TYPES = [
        ('CLOSE', 'CLOSE'),
        ('QUANTITY', 'QUANTITY'),
        ('TARGET_QUANTITY', 'TARGET_QUANTITY'),
        # TODO add 'VALUE' and 'TARGET_VALUE' order types
        ('PERCENT', 'PERCENT'),
        ('INCREASE_PERCENT', 'INCREASE_PERCENT'),
        ('TARGET_WEIGHT', 'TARGET_WEIGHT'),
    ]

    epoch = models.ForeignKey(Epoch, on_delete=models.CASCADE)
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
                check=models.Q(order_type__in=('CLOSE', )) | ~models.Q(quantity=None),
                name='check_quantity'
            ),
        ]
        indexes = [
            models.Index(fields=['epoch', 'asset', 'valid_from']),
            models.Index(fields=['target_weight_bracket_id']),
            models.Index(fields=['executed']),
            models.Index(fields=['cancelled']),
        ]


class Trade(models.Model):

    epoch = models.ForeignKey(Epoch, on_delete=models.CASCADE)
    tstamp = models.DateTimeField()
    asset = models.CharField(max_length=64)
    quantity = models.FloatField()
    price = models.FloatField()
    asset_strategy = models.CharField(max_length=64, default=DEFAULT_ASSET_STRATEGY)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)

    def __str__(self):
        return f'{model_to_dict(self)}'


class Portfolio(object):

    def __init__(self, reference: Strategy | Epoch | int):
        if isinstance(reference, int):
            self.epoch = reference
        elif isinstance(reference, Strategy):
            self.epoch = reference.last_epoch()
        elif isinstance(reference, Epoch):
            self.epoch = reference.pk

    @property
    def positions(self) -> Tuple[float, Dict[str, List[Position]]]:
        positions = list(Position.fetch_most_recent_positions(epoch=self.epoch))

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
                .filter(*queries, epoch=self.epoch, tstamp__gte=from_index)\
                .order_by("epoch", "asset", "asset_strategy", "tstamp")\
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
