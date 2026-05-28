from abc import ABC, abstractmethod
from typing import Dict, List

from src.core.base import StrategySignal


class BaseStrategy(ABC):
    name: str = ""
    weight: float = 1.0

    @abstractmethod
    def generate(self, data: Dict) -> StrategySignal:
        ...

    @abstractmethod
    def get_required_data(self) -> List[str]:
        ...
