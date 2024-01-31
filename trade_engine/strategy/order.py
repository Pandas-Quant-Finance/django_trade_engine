from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Literal

from trade_engine.models import DEFAULT_ASSET_STRATEGY, DEFAULT_BRACKET_FACTORY, DEFAULT_MAX_DATE


@dataclass
class Order:
    asset: str
    order_type: Literal['CLOSE', 'QUANTITY', 'TARGET_QUANTITY', 'PERCENT', 'INCREASE_PERCENT', 'TARGET_WEIGHT',]
    quantity: float = None
    asset_strategy: str = DEFAULT_ASSET_STRATEGY
    valid_until: datetime = DEFAULT_MAX_DATE
    limit: float = None
    stop_limit: float = None
    target_weight_bracket_id: str = DEFAULT_BRACKET_FACTORY

    def to_dict(self):
        return asdict(self)