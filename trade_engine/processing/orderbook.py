import logging
from typing import List

from django.db import transaction
from django.db.models import Q

from .. import models
from ..signals import trade_executed
from ..tickers.tick import Tick

log = logging.getLogger(__name__)

MIN_TRADE_SIZE = 0.01  # would be 1 if we don't allow fractions, currently we treat everything as fractionable


# we can provide a backtest order book or a real live order book where we send orders to and receive executed orders
@transaction.atomic()
def lala_orderbook(ticks: List[Tick]):
    trades = []
    orders = set()
    asset_ticks = {}

    for t in ticks:
        asset_ticks[t.asset] = t
        orders.update(
            models.Order.objects.filter(
                Q(valid_until__gte=t.tst) | Q(valid_until=None),
                Q(target_weights__has_key=t.asset) | Q(asset=t.asset) ,
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
