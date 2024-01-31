from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Literal


@dataclass
class Order:
    asset: str
    order_type: Literal['CLOSE', 'QUANTITY', 'TARGET_QUANTITY', 'PERCENT', 'INCREASE_PERCENT', 'TARGET_WEIGHT',]
    quantity: float = None
    asset_strategy: str = None
    valid_until: datetime = None
    limit: float = None
    stop_limit: float = None
    target_weight_bracket_id: str = None

    def __post_init__(self):
        from trade_engine.models import DEFAULT_ASSET_STRATEGY, DEFAULT_BRACKET_FACTORY, DEFAULT_MAX_DATE

        if self.target_weight_bracket_id is None:
            self.target_weight_bracket_id = str(DEFAULT_BRACKET_FACTORY())
        if self.asset_strategy is None:
            self.asset_strategy =  DEFAULT_ASSET_STRATEGY
        if self.valid_until is None:
            self.valid_until = DEFAULT_MAX_DATE

    def to_dict(self):
        return asdict(self)