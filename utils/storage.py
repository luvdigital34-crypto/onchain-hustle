import json, os, logging
from pathlib import Path
from datetime import date

logger = logging.getLogger(__name__)

DEFAULT = {
    "chat_ids": [],
    "dev_wallets": [],
    "user_wallets": {},
    "demo_portfolio": {},
    "demo_trades": [],
    "demo_positions": {},
    "daily_stats": {},
    "signal_stats": {},
    "dev_history": {},
}

class Storage:
    def __init__(self, filepath="data/storage.json"):
        self.filepath = filepath
        Path(os.path.dirname(filepath)).mkdir(parents=True, exist_ok=True)
        if not os.path.exists(filepath):
            self._save(DEFAULT.copy())

    def _load(self):
        with open(self.filepath, "r") as f:
            data = json.load(f)
        for k, v in DEFAULT.items():
            if k not in data:
                data[k] = v
        return data

    def _save(self, data):
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_chat_ids(self): return self._load()["chat_ids"]
    def add_chat_id(self, cid):
        d = self._load()
        if str(cid) not in d["chat_ids"]:
            d["chat_ids"].append(str(cid))
            self._save(d)

    def get_dev_wallets(self): return self._load()["dev_wallets"]
    def add_dev_wallet(self, address, label=""):
        d = self._load()
        if any(w["address"] == address for w in d["dev_wallets"]):
            return False
        d["dev_wallets"].append({"address": address, "label": label or address[:8]})
        self._save(d)
        return True
    def remove_dev_wallet(self, address):
        d = self._load()
        before = len(d["dev_wallets"])
        d["dev_wallets"] = [w for w in d["dev_wallets"] if w["address"] != address]
        self._save(d)
        return len(d["dev_wallets"]) < before

    def get_user_wallet(self, chat_id): return self._load()["user_wallets"].get(str(chat_id), "")
    def set_user_wallet(self, chat_id, address):
        d = self._load()
        d["user_wallets"][str(chat_id)] = address
        self._save(d)

    def get_demo_portfolio(self, chat_id):
        return self._load()["demo_portfolio"].get(str(chat_id), {"sol": 10.0, "pnl": 0.0, "trades": 0})
    def save_demo_portfolio(self, chat_id, portfolio):
        d = self._load()
        d["demo_portfolio"][str(chat_id)] = portfolio
        self._save(d)

    def get_demo_trades(self): return self._load().get("demo_trades", [])
    def add_demo_trade(self, trade):
        d = self._load()
        d["demo_trades"].append(trade)
        d["demo_trades"] = d["demo_trades"][-200:]
        self._save(d)

    def get_open_positions(self, chat_id=None):
        d = self._load()
        positions = d.get("demo_positions", {})
        if chat_id is not None:
            return positions.get(str(chat_id), [])
        return positions

    def add_open_position(self, chat_id, position):
        d = self._load()
        positions = d.setdefault("demo_positions", {})
        positions.setdefault(str(chat_id), []).append(position)
        self._save(d)

    def remove_open_position(self, chat_id, mint):
        d = self._load()
        positions = d.setdefault("demo_positions", {})
        chat_positions = positions.get(str(chat_id), [])
        positions[str(chat_id)] = [p for p in chat_positions if p.get("mint") != mint]
        self._save(d)

    def get_all_open_positions_flat(self):
        d = self._load()
        result = []
        for chat_id, positions in d.get("demo_positions", {}).items():
            for p in positions:
                result.append((chat_id, p))
        return result

    def get_today_stats(self, chat_id):
        today = str(date.today())
        d = self._load()
        chat_stats = d.get("daily_stats", {}).get(str(chat_id), {})
        return chat_stats.get(today, {"pnl": 0.0, "tp": 0, "sl": 0, "wins": 0, "losses": 0})

    def update_today_stats(self, chat_id, pnl_delta, is_tp=False, is_sl=False):
        today = str(date.today())
        d = self._load()
        daily = d.setdefault("daily_stats", {})
        chat_stats = daily.setdefault(str(chat_id), {})
        today_stats = chat_stats.setdefault(today, {"pnl": 0.0, "tp": 0, "sl": 0, "wins": 0, "losses": 0})
        today_stats["pnl"] += pnl_delta
        if is_tp:
            today_stats["tp"] += 1
            today_stats["wins"] += 1
        if is_sl:
            today_stats["sl"] += 1
            today_stats["losses"] += 1
        self._save(d)
        return today_stats

    def get_signal_stats(self):
        return self._load().get("signal_stats", {})

    def record_signal_result(self, signal_names, won):
        d = self._load()
        stats = d.setdefault("signal_stats", {})
        for name in signal_names:
            s = stats.setdefault(name, {"wins": 0, "losses": 0})
            if won:
                s["wins"] += 1
            else:
                s["losses"] += 1
        self._save(d)

    def get_signal_weight_multiplier(self, signal_name):
        stats = self.get_signal_stats().get(signal_name)
        if not stats:
            return 1.0
        total = stats["wins"] + stats["losses"]
        if total < 5:
            return 1.0
        win_rate = stats["wins"] / total
        return round(max(0.5, min(1.5, 0.5 + win_rate)), 2)

    def get_dev_history(self, address):
        return self._load().get("dev_history", {}).get(address, {"launched": 0, "rugged": 0, "good": 0})

    def record_dev_outcome(self, address, outcome):
        d = self._load()
        history = d.setdefault("dev_history", {})
        entry = history.setdefault(address, {"launched": 0, "rugged": 0, "good": 0})
        entry["launched"] += 1
        if outcome == "rugged":
            entry["rugged"] += 1
        elif outcome == "good":
            entry["good"] += 1
        self._save(d)
