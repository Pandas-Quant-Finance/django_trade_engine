import logging

from django.db import transaction

from .. import models
from ..tickers.tick import Tick

log = logging.getLogger(__name__)


@transaction.atomic()
def position_roll_forward(*ticks: Tick):
    for tick in ticks:
        if tick.bid > tick.ask:
            # undocumented feature to catch limit orders from candle stick data, ignore if bid > ask
            continue

        for pos in models.Position.fetch_most_recent_positions(asset=tick.asset):
            if tick.tst > pos.tstamp:
                # if we have a newer quote then create a new timeseries entry else update
                pos.pk = None
                pos.tstamp = tick.tst

            pos.last_price = tick.bid if pos.quantity > 0 else tick.ask
            pos.save()


@transaction.atomic()
def position_update(*trades: models.Trade):
    log.info(f"execute trades: {trades}")
    epochs = {trade.epoch_id for trade in trades}
    positions = {(pos.epoch, pos.asset, pos.asset_strategy): pos for pos in models.Position.fetch_most_recent_positions(epochs)}
    cash = {t.epoch: models.Position.fetch_most_recent_cash(t.epoch) for t in trades}
    cash_updates = {t.epoch: 0 for t in trades}
    max_tsts = {}

    for trade in trades:
        if trade.asset == models.CASH_ASSET:
            log.warning(f"you can't trade the cash asset {trade}")
            continue

        # when a trade has executed we need to create or increase / decrease positions
        if (trade.epoch, trade.asset, trade.asset_strategy) not in positions:
            # create
            models.Position(
                epoch=trade.epoch,
                tstamp=trade.tstamp,
                asset=trade.asset,
                asset_strategy=trade.asset_strategy,
                quantity=trade.quantity,
                last_price=trade.price,
            ).save()
        else:
            # update current position
            pos = positions[(trade.epoch, trade.asset, trade.asset_strategy)]
            pos.tstamp = trade.tstamp
            pos.quantity += trade.quantity
            pos.last_price = trade.price
            pos.save()

        cash_updates[trade.epoch] += (trade.quantity * trade.price)
        max_tsts[trade.epoch] = max(max_tsts.get(trade.epoch, trade.tstamp), trade.tstamp)

    # update all cash positions as well
    for strategy, amount in cash_updates.items():
        cash[strategy].pk = None
        cash[strategy].tstamp = max_tsts[strategy]
        cash[strategy].quantity -= amount
        cash[strategy].save()
