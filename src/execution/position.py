from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from src.core.base import Position as PositionData
from src.data.store import PositionStore


class PositionManager:
    def __init__(self):
        self.store = PositionStore()

    def get_all(self) -> List[dict]:
        return self.store.get_all_positions()

    def get(self, code: str) -> Optional[dict]:
        return self.store.get_position(code)

    def update_price(self, code: str, price: float):
        pos = self.store.get_position(code)
        if not pos:
            return
        volume = pos["volume"]
        cost = pos["cost_price"]
        market_value = volume * price
        profit_amount = market_value - volume * cost
        profit_pct = (price - cost) / cost * 100 if cost > 0 else 0
        updated = PositionData(
            code=code,
            name=pos["name"],
            volume=volume,
            cost_price=cost,
            current_price=price,
            market_value=market_value,
            profit_pct=round(profit_pct, 2),
            profit_amount=round(profit_amount, 2),
            updated_at=datetime.now().isoformat(),
        )
        self.store.save_position(updated)

    def open_position(self, code: str, name: str, price: float, volume: int):
        pos = PositionData(
            code=code, name=name, volume=volume,
            cost_price=price, current_price=price,
            market_value=price * volume,
            profit_pct=0, profit_amount=0,
            updated_at=datetime.now().isoformat(),
        )
        self.store.save_position(pos)

    def close_position(self, code: str):
        pos = self.store.get_position(code)
        if pos:
            closed = PositionData(
                code=code, name=pos["name"], volume=0,
                cost_price=0, current_price=0,
                market_value=0, profit_pct=0, profit_amount=0,
                updated_at=datetime.now().isoformat(),
            )
            self.store.save_position(closed)

    def get_total_value(self) -> float:
        positions = self.get_all()
        return sum(p["market_value"] for p in positions if p["volume"] > 0)

    def get_total_profit(self) -> float:
        positions = self.get_all()
        return sum(p["profit_amount"] for p in positions if p["volume"] > 0)
