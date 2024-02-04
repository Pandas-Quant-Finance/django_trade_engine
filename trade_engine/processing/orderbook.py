import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import List, Iterable, Dict, Tuple, Set

from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, Exists

from .. import models
from ..models import Order
from ..signals import trade_executed
from ..tickers.tick import Tick

log = logging.getLogger(__name__)

MIN_TRADE_SIZE = 0.01  # only trade if we reach 1cent trade equivalent, should be configured per orderbook

# we need to eventually make this a temp table of a in-memory database
LATEST_TICKS = defaultdict(dict)


@transaction.atomic()
def new_orderbook(*ticks: Tick, stop_propagation: bool = False):
    # keep global lookup table for latest tick
    ticks = aggregate_ticks(ticks)
    update_ticks(ticks.values())

    # get orders ready for trade execution
    orders = fetch_orders(ticks.values())
    tradeable_orders = get_orders_with_quantity(orders)
    tradeable_orders = check_limits(tradeable_orders)

    # convert orders to executable trades
    trades = make_trades(tradeable_orders)
    trades, orders = filter_minium_trade_volume(trades)

    # execute trades
    if len(trades) > 0 and not stop_propagation:
        trade_executed.send(sender=models.Order.__class__, trades=trades)

    # mark orders executed
    mark_orders_executed(orders)


def aggregate_ticks(ticks: Iterable[Tick]) -> Dict[str, Tick]:
    #{t.tst: t.asset for t in sorted(ticks, key=lambda t: t.tst)}
    return {t.asset: t for t in sorted(ticks, key=lambda t: t.tst)}


def update_ticks(ticks: Iterable[Tick]):
    for t in ticks:
        # make sure we don't remember special limit triggering ticks
        if t.bid <= t.ask:
            LATEST_TICKS[t.epoch_id][t.asset] = t


def fetch_orders(ticks: Iterable[Tick]) -> Dict[str, Dict[str, Set[models.Order]]]:
    orders = defaultdict(lambda: defaultdict(set))
    epoch_time_ticks = defaultdict(lambda: defaultdict(set))

    # prepare ticks for in query
    for tick in ticks:
        epoch_time_ticks[tick.epoch_id][tick.tst].add(tick.asset)

    for epoch_id, time_ticks in epoch_time_ticks.items():
        for tst, assets in time_ticks.items():
            main_query = Q(valid_until__gte=tst, epoch__pk=epoch_id, executed=False, cancelled=False, valid_from__lt=tst)
            subquery = Exists(models.Order.objects.filter(main_query, asset__in=assets, target_weight_bracket_id=OuterRef('target_weight_bracket_id')))
            for o in models.Order.objects.filter(main_query, subquery).all():
                orders[o.epoch_id][o.target_weight_bracket_id].add(o)

    return orders


def get_orders_with_quantity(orders: Dict[str, Dict[str, Set[models.Order]]]) -> List[Tuple[float, Tick, models.Order]]:
    quantity_orders = []
    for bracket_orders in orders.values():
        for bracket_id, order_set in bracket_orders.items():
            for o in _get_order_with_quantity(*order_set):
                quantity_orders.append(o)

    return quantity_orders


def _get_order_with_quantity(order: models.Order, *bracket_orders: models.Order) -> Tuple[float, float, models.Order] | List[Tuple[float, Tick, models.Order]]:
    # TODO we need the most recent tick for each asset which is not a high/low tick and return (quantity, price, order)

    def get_postion_for_order(order) -> models.Position:
        return (
            [p for p in models.Position.fetch_most_recent_positions(epoch=order.epoch_id, asset=order.asset, include_zero=True) if p.asset_strategy == order.asset_strategy]
            or
            [None]
        )[0]

    if order.order_type == 'CLOSE':
        pos = get_postion_for_order(order)
        yield (0 if pos is None else -pos.quantity), LATEST_TICKS[order.epoch_id][order.asset], order
    elif order.order_type == 'TARGET_QUANTITY':
        pos = get_postion_for_order(order)
        yield (0 if pos is None else (order.quantity - pos.quantity)), LATEST_TICKS[order.epoch_id][order.asset], order
    elif order.order_type == 'PERCENT':
        cash = models.Position.objects.filter(epoch=order.epoch_id, asset=models.CASH_ASSET).first()
        latest_tick = LATEST_TICKS[order.epoch_id][order.asset]

        if order.quantity < 0 and (pos := get_postion_for_order(order)) is not None:
            # if percent is < 0 and we have a position, we want to decrease the position
            quantity = ((1 + order.quantity) * pos.value) / (latest_tick.ask if pos.quantity > 0 else latest_tick.bid)
        else:
            quantity = (order.quantity * cash.value) / (latest_tick.ask if order.quantity > 0 else latest_tick.bid)

        yield (0 if cash.value < 0 or quantity < MIN_TRADE_SIZE else quantity), latest_tick, order
    elif order.order_type == 'INCREASE_PERCENT':
        latest_tick = LATEST_TICKS[order.epoch_id][order.asset]
        pos = get_postion_for_order(order)
        quantity = ((1 + order.quantity) * pos.value) / (latest_tick.ask if order.quantity > 0 else latest_tick.bid)
        yield quantity, latest_tick, order
    elif order.order_type == 'TARGET_WEIGHT':
        # get all orders from the same target_weight_bracket_id
        target_weight_orders = {o.asset: o for o in [order, *bracket_orders]}

        # get the portfolio
        portfolio_value, positions = models.Portfolio(order.epoch).positions
        positions = {a: p for a, p in positions.items() if p.asset_strategy == order.asset_strategy}

        # keys in the portfolio but not in the target weighs need to be closed
        for a, pos in positions.items():
            if a not in target_weight_orders and a != models.CASH_ASSET:
                target_weight_orders[a] = models.Order(
                    epoch=order.epoch, asset=a, asset_strategy=order.asset_strategy, order_type='TARGET_WEIGHT',
                    valid_from=order.valid_from, valid_until=order.valid_from, quantity=0, generated=True,
                )

        # calculate quantities
        for a, o in target_weight_orders.items():
            tick = LATEST_TICKS[order.epoch_id].get(a, None)
            if tick is None:
                log.warning(f"No price available for: {a}, skip order: {order}")
                continue

            # use calculate quantity of order
            price = (tick.ask + tick.bid) / 2
            qty = (portfolio_value * o.quantity) / price
            if a in positions:
                qty -= positions[a].quantity

            yield qty, tick, target_weight_orders[a]
    else:
        yield order.quantity, LATEST_TICKS[order.epoch_id][order.asset], order


def check_limits(orders: Iterable[Tuple[float, Tick, Order]]) -> List[Tuple[float, float, Tick, Order]]:
    # check limit if limit order using most recent tick, eventually update the price
    # TODO implement limit checks ...
    return [(o[0], o[1].ask if o[0] > 0 else o[1].bid, *o[1:]) for o in orders]


def make_trades(orders: Iterable[Tuple[float, float, Tick, Order]]) -> List[Tuple[models.Trade, models.Order]]:
    return [(models.Trade(epoch=o.epoch, tstamp=t.tst, asset=t.asset, quantity=q, price=p, asset_strategy=o.asset_strategy, order=o), o) for q, p, t, o in orders]


def filter_minium_trade_volume(trades: List[Tuple[models.Trade, models.Order]]) -> Tuple[List[models.Trade], List[models.Order]]:
    executeable_trades = []
    orders = []

    for t, o in trades:
        if abs(t.quantity * t.price) >= MIN_TRADE_SIZE and abs(t.quantity) > 0:
            executeable_trades.append(t)
        else:
            o.cancelled = True

        orders.append(o)
    return executeable_trades, orders


def mark_orders_executed(orders: Iterable[Tuple[float, float, Tick, Order]]):
    for order in orders:
        order.executed = True
        order.save()
