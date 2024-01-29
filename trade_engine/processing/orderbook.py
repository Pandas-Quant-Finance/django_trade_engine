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


# we can provide a backtest order book or a real live order book where we send orders to and receive executed orders
@transaction.atomic()
def lala_orderbook(*ticks: Tick):
    trades = []
    orders = set()
    asset_ticks = {}

    for t in ticks:
        asset_ticks[t.asset] = t
        orders.update(
            models.Order.objects.filter(
                Q(valid_until__gte=t.tst) | Q(valid_until=None),
                Q(target_weights__has_key=t.asset) | Q(asset=t.asset),
                executed=False,
                cancelled=False,
                valid_from__lt=t.tst  # orders strictly placed before the tick arrived.
            ).all()
        )

    # early exit if nothing to do
    if len(orders) <= 0:
        log.debug("Nothing to do", ticks)
        return

    # fetch portfolios for target weight orders
    needed_portfolio_strategies = {o.strategy for o in orders if o.order_type in ('PERCENT', 'TARGET_WEIGHT')}
    portfolios = {s: models.Portfolio(s) for s in needed_portfolio_strategies}

    # order all orders by quantity (sells first)
    sorted(orders, key=lambda x: x.quantity or 0)

    for o in orders:
        order_quantity = o.quantity

        if o.order_type == 'CLOSE':
            # use position quantity for close orders
            pos = models.Position.objects.filter(strategy=o.strategy, asset=o.asset, asset_strategy=o.asset_strategy).first()
            # update quantity
            if pos is None: continue
            order_quantity = pos.quantity

        if o.order_type == 'TARGET_QUANTITY':
            pos = models.Position.objects.filter(strategy=o.strategy, asset=o.asset, asset_strategy=o.asset_strategy).first()
            if pos is not None:
                order_quantity = o.quantity - pos.quantity

        if o.order_type == 'PERCENT':
            cash = models.Position.objects.filter(strategy=o.strategy, asset=models.CASH_ASSET).first()
            quantity = (o.quantity * cash.value) / (asset_ticks[o.asset].ask if o.quantity > 0 else asset_ticks[o.asset].bid)
            if cash.value < 0 or quantity < MIN_TRADE_SIZE:
                log.warning(f"{o} insufficient funds")
                o.cancelled = True
                o.save()
                continue
            else:
                order_quantity = quantity

        if o.order_type == 'TARGET_WEIGHT':
            # convert target weight orders to quantity orders
            assert o.target_weights is not None, 'Target weights were not provided'
            portfolio_value, positions = portfolios[o.strategy].positions

            # assets we have and want to trade/change
            delta_weights = {a: w - positions[a].weight if a in positions else w for a, w in o.target_weights.items() if a != models.CASH_ASSET}

            # keys in the portfolio but not in the target weighs need to be closed
            for a, pos in positions.items():
                if a not in o.target_weights and a != models.CASH_ASSET:
                    delta_weights[a] = -pos.weight

            # find reasonable timestamp
            tst = max([t.tst for t in ticks])

            # convert weights to quantities:
            # use price from ticks or from the portfolio. if no price is available continue and wait for ticks to be
            # available. this can be a problem when all realtime ticks don't come together. we then need some kind of
            # end of day tick for all assets. we need to solve this problem once we introduce a realtime orderbook with
            # a broker. TODO We could remember every last tick in a global variable though.

            for a, dw in delta_weights.items():
                price = asset_ticks.get(a, positions.get(a, None))
                if price is None:
                    log.warning(f"No price available for: {a}, skip oder: {o}")
                    continue
                elif isinstance(price, models.Position):
                    price = price.last_price
                elif isinstance(price, Tick):
                    price = price.ask if dw > 0 else price.bid

                # use delta weights for quantity and append all trades. continue (skip limit check) afterward
                qty = (portfolio_value * dw) / price
                trades.append(
                    models.Trade(
                        o.strategy, tst, a, qty, price, order=o.pk
                    )
                )

            # we eventually converted orders into Trades, limit orders are currently not possible for target weights,
            # so we skip the limit handling
            o.executed = True
            o.save()
            continue

        # filter orders executable within limits
        if o.stop_limit is not None and not o.stop_limit_activated:
            if not (o.stop_limit > asset_ticks[o.asset].ask if order_quantity > 0 else o.stop_limit < asset_ticks[o.asset].bid):
                o.stop_limit_activated = True
                o.save()
                continue

        if o.limit is not None and (o.stop_limit is None or o.stop_limit_activated):
            if not (o.limit > asset_ticks[o.asset].ask if order_quantity > 0 else o.limit < asset_ticks[o.asset].bid):
                continue

        # execute orders
        price = asset_ticks[o.asset].ask if order_quantity > 0 else asset_ticks[o.asset].bid
        trades.append(
            models.Trade(
                o.strategy, asset_ticks[o.asset].tst, o.asset, order_quantity, o.limit or price, order=o.pk
            )  # we eventually convert Trade into a model and save it to the database, see comment in Trade class
        )

        o.executed = True
        o.save()

    # send all trades
    trade_executed.send(sender=models.Order.__class__, trades=trades)


@transaction.atomic()
def new_orderbook(*ticks: Tick, stop_propagation: bool = False):
    ticks = aggregate_ticks(ticks)
    update_ticks(ticks.values())

    orders = fetch_orders(ticks.values())
    tradeable_orders = get_orders_with_quantity(orders)
    tradeable_orders = check_limits(tradeable_orders)

    trades = make_trades(tradeable_orders)
    trades = filter_minium_trade_volume(trades)

    if len(trades) > 0 and not stop_propagation:
        trade_executed.send(sender=models.Order.__class__, trades=trades)

    mark_orders_executed(tradeable_orders)


def aggregate_ticks(ticks: Iterable[Tick]) -> Dict[str, Tick]:
    return {t.asset: t for t in sorted(ticks, key=lambda t: t.tst)}


def update_ticks(ticks: Iterable[Tick]):
    for t in ticks:
        # make sure we don't remember special limit triggering ticks
        if t.bid <= t.ask:
            LATEST_TICKS[t.strategy_id][t.asset] = t


def fetch_orders(ticks: Iterable[Tick]) -> Dict[str, Dict[str, Set[models.Order]]]:
    orders = defaultdict(lambda: defaultdict(set))

    for t in ticks:
        main_query = Q(valid_until__gte=t.tst, strategy__pk=t.strategy_id, executed=False, cancelled=False, valid_from__lt=t.tst)
        subquery = Exists(models.Order.objects.filter(main_query, asset=t.asset, target_weight_bracket_id=OuterRef('target_weight_bracket_id')))
        for o in models.Order.objects.filter(main_query, subquery).all():
            orders[o.strategy_id][o.target_weight_bracket_id].add(o)

    return orders


def get_orders_with_quantity(orders: Dict[str, Dict[str, Set[models.Order]]]) -> List[Tuple[float, float, models.Order]]:
    quantity_orders = []
    for bracket_orders in orders.values():
        for bracket_id, order_set in bracket_orders.items():
            for o in _get_order_with_quantity(*order_set):
                quantity_orders.append(o)

    return quantity_orders


def _get_order_with_quantity(order: models.Order, *bracket_orders: models.Order) -> Tuple[float, float, models.Order] | List[Tuple[float, Tick, models.Order]]:
    # TODO we need the most recent tick for each asset which is not a high/low tick and return (quantity, price, order)

    if order.order_type == 'CLOSE':
        pos = models.Position.objects.filter(
            strategy=order.strategy, asset=order.asset, asset_strategy=order.asset_strategy
        ).first()

        yield (0 if pos is None else -pos.quantity), LATEST_TICKS[order.strategy.pk][order.asset], order
    elif order.order_type == 'TARGET_QUANTITY':
        pos = models.Position.objects.filter(
            strategy=order.strategy, asset=order.asset, asset_strategy=order.asset_strategy
        ).first()

        yield (0 if pos is None else (order.quantity - pos.quantity)), LATEST_TICKS[order.strategy.pk][order.asset], order
    elif order.order_type == 'PERCENT':
        cash = models.Position.objects.filter(strategy=order.strategy, asset=models.CASH_ASSET).first()
        latest_tick = LATEST_TICKS[order.strategy.pk][order.asset]
        quantity = (order.quantity * cash.value) / (latest_tick.ask if order.quantity > 0 else latest_tick.bid)
        yield (0 if cash.value < 0 or quantity < MIN_TRADE_SIZE else quantity), latest_tick, order

    elif order.order_type == 'TARGET_WEIGHT':
        # get all orders from the same target_weight_bracket_id
        target_weight_orders = {o.asset: o for o in [order, *bracket_orders]}

        # get the portfolio
        portfolio_value, positions = models.Portfolio(order.strategy).positions

        # keys in the portfolio but not in the target weighs need to be closed
        for a, pos in positions.items():
            if a not in target_weight_orders and a != models.CASH_ASSET:
                target_weight_orders[a] = models.Order(
                    strategy=order.strategy, asset=a, asset_strategy=order.asset_strategy, order_type='TARGET_WEIGHT',
                    valid_from=order.valid_from, valid_until=order.valid_from, quantity=0, generated=True,
                )

        # calculate quantities
        for a, o in target_weight_orders.items():
            tick = LATEST_TICKS[order.strategy_id].get(a, None)
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
        yield order.quantity, LATEST_TICKS[order.strategy.pk][order.asset], order


def check_limits(orders: Iterable[Tuple[float, Tick, Order]]) -> List[Tuple[float, float, Tick, Order]]:
    # check limit if limit order using most recent tick, eventually update the price
    # TODO implement limit checks ...
    return [(o[0], o[1].ask if o[0] > 0 else o[1].bid, *o[1:]) for o in orders]


def make_trades(orders: Iterable[Tuple[float, float, Tick, Order]]) -> List[models.Trade]:
    return [models.Trade(o.strategy, t.tst, o.asset, q, p, order=o.pk) for q, p, t, o in orders]


def filter_minium_trade_volume(trades: List[models.Trade]) -> List[models.Trade]:
    return list(filter(lambda t: abs(t.quantity * t.price) >= MIN_TRADE_SIZE, trades))


def mark_orders_executed(orders: Iterable[Tuple[float, float, Tick, Order]]):
    for q, _, _, order in orders:
        order.executed = True
        if q == 0: order.cancelled = True
        order.save()