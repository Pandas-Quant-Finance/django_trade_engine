from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tick:

    asset: str
    tst: datetime
    bid: float = None
    ask: float = None
    volume: float = None
