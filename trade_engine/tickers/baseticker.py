from abc import abstractmethod
from .tick import Tick


class BaseTicker(object):

    @abstractmethod
    def send_tick(self, *ticks: Tick):
        pass
