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


class RealBroker(Broker):
    """实盘券商接口基类 - 继承此类实现具体券商对接"""

    def __init__(self):
        self.trade_store = TradeStore()
        self._connected = False

    def connect(self) -> bool:
        raise NotImplementedError

    def buy(self, order: Order) -> OrderResult:
        raise NotImplementedError

    def sell(self, order: Order) -> OrderResult:
        raise NotImplementedError

    def get_position(self, code: str) -> Optional[dict]:
        raise NotImplementedError

    def get_account_balance(self) -> float:
        raise NotImplementedError


class XtQuantBroker(RealBroker):
    """迅投QMT券商接口 (需安装xtquant)"""

    def connect(self) -> bool:
        try:
            from xtquant import xtdata
            self._connected = True
            return True
        except ImportError:
            return False

    def buy(self, order: Order) -> OrderResult:
        return OrderResult(success=False, message="未实现: QMT下单需配置交易终端")

    def sell(self, order: Order) -> OrderResult:
        return OrderResult(success=False, message="未实现: QMT下单需配置交易终端")

    def get_position(self, code: str) -> Optional[dict]:
        return None

    def get_account_balance(self) -> float:
        return 0.0


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
