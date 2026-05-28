from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.core.base import Order
from src.execution.order import OrderFactory
from src.data.store import TradeStore


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[int] = None
    message: str = ""
    executed_price: float = 0.0
    executed_volume: int = 0


class Broker(ABC):
    @abstractmethod
    def buy(self, order: Order) -> OrderResult:
        ...

    @abstractmethod
    def sell(self, order: Order) -> OrderResult:
        ...


class MockBroker(Broker):
    def __init__(self):
        self.trade_store = TradeStore()
        self._trade_counter = 0

    def buy(self, order: Order) -> OrderResult:
        self._trade_counter += 1
        result = OrderResult(
            success=True,
            executed_price=order.price,
            executed_volume=order.volume,
            order_id=self._trade_counter,
            message="模拟买入成交",
        )
        executed = OrderFactory.create_market_order(
            code=order.code, name=order.name, direction="buy",
            price=order.price, volume=order.volume,
            reason=order.reason, signal_id=order.signal_id,
        )
        executed.status = "filled"
        executed.executed_at = datetime.now().isoformat()
        executed.fee = round(order.amount * 0.00025, 2)
        self.trade_store.save_order(executed)
        return result

    def sell(self, order: Order) -> OrderResult:
        self._trade_counter += 1
        result = OrderResult(
            success=True,
            executed_price=order.price,
            executed_volume=order.volume,
            order_id=self._trade_counter,
            message="模拟卖出成交",
        )
        executed = OrderFactory.create_market_order(
            code=order.code, name=order.name, direction="sell",
            price=order.price, volume=order.volume,
            reason=order.reason, signal_id=order.signal_id,
        )
        executed.status = "filled"
        executed.executed_at = datetime.now().isoformat()
        executed.fee = round(order.amount * 0.00025, 2)
        self.trade_store.save_order(executed)
        return result
