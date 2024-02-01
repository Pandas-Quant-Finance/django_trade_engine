from typing import List, Tuple, Dict, Callable

import pandas as pd
import pytz
from dateutil.tz import tz

from trade_engine.signals import tick
from .baseticker import BaseTicker
from .tick import Tick


class PandasReplayTicker(BaseTicker):

    # we could sample a slippage from the standard deviation and add it to the tick

    def __init__(
            self,
            df: pd.DataFrame | Dict[str, pd.DataFrame],
            level: int = 0,
            slippage_std: float = 0.0,
            slippage_fixed: float = 0.0,
            # sequence of prices, note: High > Low because we want to catch all limit orders
            prices: List[Tuple[str, str]] = (('Open', 'Open'), ('High', 'Low'), ('Close', 'Close')),
            volume=None,
     ):
        if isinstance(df, dict): df = pd.concat(df.values(), axis=1, keys=df.keys())
        self.df = df if level == 0 else df.swaplevel(0, 1, axis=1)
        self.index = df.index
        self.level = level
        self.assets = df.columns.get_level_values(level).unique()
        self.prices = prices
        self.volume = volume

    def send_tick(self, *ticks: Tick):
        tick.send(sender=self.__class__, ticks=ticks)

    def start(self, epoch_id: int, callback: Callable[[List[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], None] = None):
        for date in self.index:
            if isinstance(date, pd.Timestamp):
                date = date.to_pydatetime()

            # bid/ask = open -/+ slippage volumne = volume
            ticks = []
            for p in self.prices:
                ticks = [
                    Tick(
                        epoch_id,
                        a,
                        pytz.utc.localize(date) if date.tzinfo is None else date,
                        self.df.loc[date, (a, p[0])],
                        self.df.loc[date, (a, p[1])],
                        None if self.volume is None else self.df.loc[date, (a, self.volume)]
                    ) for a in self.assets
                ]

                self.send_tick(*ticks)

            if callable(callback):
                callback(ticks, self.df.loc[:date])
