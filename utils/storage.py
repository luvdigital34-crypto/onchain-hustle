import json, os, logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT = {
    "chat_ids": [],
    "dev_wallets": [],
    "user_wallets": {},
    "demo_portfolio": {},
    "demo_trades": [],
    "demo_positions": {},
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
        d["demo_trades"] = d["demo_trades"][-100:]
        self._save(d)

    # ---- Positions ouvertes (démo) ----
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
        """Retourne [(chat_id, position), ...] pour tous les utilisateurs."""
        d = self._load()
        result = []
        for chat_id, positions in d.get("demo_positions", {}).items():
            for p in positions:
                result.append((chat_id, p))
        return result
