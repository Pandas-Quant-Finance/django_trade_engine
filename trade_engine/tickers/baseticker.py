from abc import abstractmethod
from typing import Callable, List

import pandas as pd

from .tick import Tick


class BaseTicker(object):

    @abstractmethod
    def send_tick(self, *ticks: Tick):
        pass

    @abstractmethod
    def start(self, strategy_id: str, callback: Callable[[List[Tick], pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None], None] = None):
        pass
