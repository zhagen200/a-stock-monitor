from pathlib import Path
from typing import Any
import yaml


class Settings:
    _instance = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: str = "config/settings.yaml") -> dict:
        config_path = Path(__file__).parent.parent.parent / path
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}
        return self._data

    @property
    def data(self) -> dict:
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def get_watchlist(self) -> list:
        return self._data.get("watchlist", {}).get("stocks", [])

    def get_funds(self) -> list:
        return self._data.get("watchlist", {}).get("funds", [])

    def get_notify_config(self) -> dict:
        return self._data.get("notify", {})

    def get_llm_config(self) -> dict:
        return self._data.get("llm", {})


settings = Settings()
