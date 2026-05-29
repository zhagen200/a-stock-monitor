"""
持仓与关注池数据管理
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HOLDINGS_FILE = DATA_DIR / "holdings.json"
WATCHPOOL_FILE = DATA_DIR / "watch_pool.json"


def _load_json(filepath: Path) -> list:
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_json(filepath: Path, data: list):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 持仓管理 ──────────────────────────────────────────

def get_holdings() -> List[Dict]:
    """获取所有持仓"""
    return _load_json(HOLDINGS_FILE)


def add_holding(code: str, name: str, cost: float, shares: int):
    """添加持仓"""
    holdings = get_holdings()
    # 检查是否已存在
    for h in holdings:
        if h["code"] == code:
            h["cost"] = cost
            h["shares"] = shares
            h["updated_at"] = datetime.now().isoformat()
            _save_json(HOLDINGS_FILE, holdings)
            return
    holdings.append({
        "code": code,
        "name": name,
        "cost": cost,
        "shares": shares,
        "added_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    })
    _save_json(HOLDINGS_FILE, holdings)


def update_holding(code: str, cost: float = None, shares: int = None):
    """更新持仓"""
    holdings = get_holdings()
    for h in holdings:
        if h["code"] == code:
            if cost is not None:
                h["cost"] = cost
            if shares is not None:
                h["shares"] = shares
            h["updated_at"] = datetime.now().isoformat()
            _save_json(HOLDINGS_FILE, holdings)
            return


def sell_holding(code: str, sell_price: float = 0, sell_shares: int = 0):
    """卖出持仓（标记为已卖出，或完全移除）"""
    holdings = get_holdings()
    new_holdings = []
    sold = None
    for h in holdings:
        if h["code"] == code:
            if sell_shares >= h["shares"] or sell_shares == 0:
                # 全部卖出
                sold = h
                sold["sold_at"] = datetime.now().isoformat()
                sold["sell_price"] = sell_price
                continue
            else:
                # 部分卖出
                h["shares"] -= sell_shares
                h["updated_at"] = datetime.now().isoformat()
        new_holdings.append(h)
    _save_json(HOLDINGS_FILE, new_holdings)
    return sold


def delete_holding(code: str):
    """删除持仓记录"""
    holdings = get_holdings()
    holdings = [h for h in holdings if h["code"] != code]
    _save_json(HOLDINGS_FILE, holdings)


# ── 关注池管理 ────────────────────────────────────────

def get_watch_pool() -> List[Dict]:
    """获取关注池"""
    return _load_json(WATCHPOOL_FILE)


def add_to_watch(code: str, name: str, source: str = "manual", reason: str = ""):
    """添加到关注池"""
    pool = get_watch_pool()
    for w in pool:
        if w["code"] == code:
            return  # 已存在
    pool.append({
        "code": code,
        "name": name,
        "source": source,
        "reason": reason,
        "added_at": datetime.now().isoformat(),
    })
    _save_json(WATCHPOOL_FILE, pool)


def remove_from_watch(code: str):
    """从关注池移除"""
    pool = get_watch_pool()
    pool = [w for w in pool if w["code"] != code]
    _save_json(WATCHPOOL_FILE, pool)


def get_all_monitor_codes() -> List[str]:
    """获取所有监控的股票代码（持仓 + 关注池）"""
    codes = set()
    for h in get_holdings():
        codes.add(h["code"])
    for w in get_watch_pool():
        codes.add(w["code"])
    return list(codes)
