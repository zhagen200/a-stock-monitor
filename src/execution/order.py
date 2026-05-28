from datetime import datetime

from src.core.base import Order


class OrderFactory:
    @staticmethod
    def create_market_order(
        code: str, name: str, direction: str,
        price: float, volume: int, reason: str = "",
        signal_id: int = None,
    ) -> Order:
        return Order(
            code=code,
            name=name,
            direction=direction,
            order_type="market",
            price=price,
            volume=volume,
            amount=price * volume,
            reason=reason,
            signal_id=signal_id,
            created_at=datetime.now().isoformat(),
        )

    @staticmethod
    def create_limit_order(
        code: str, name: str, direction: str,
        price: float, volume: int, reason: str = "",
        signal_id: int = None,
    ) -> Order:
        return Order(
            code=code,
            name=name,
            direction=direction,
            order_type="limit",
            price=price,
            volume=volume,
            amount=price * volume,
            reason=reason,
            signal_id=signal_id,
            created_at=datetime.now().isoformat(),
        )
