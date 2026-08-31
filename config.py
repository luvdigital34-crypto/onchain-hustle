import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    GROQ_API_KEY: str   = os.getenv("GROQ_API_KEY", "")
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")
    DATA_FILE: str      = "data/storage.json"
    WALLET_INTERVAL: int = int(os.getenv("WALLET_INTERVAL", "30"))
    TREND_INTERVAL: int  = int(os.getenv("TREND_INTERVAL", "300"))

    DAILY_PROFIT_TARGET: float = float(os.getenv("DAILY_PROFIT_TARGET", "1.0"))   # SOL — stop trading pour la journée si atteint
    DAILY_LOSS_LIMIT: float    = float(os.getenv("DAILY_LOSS_LIMIT", "4.0"))      # SOL — devient très sélectif si atteint

    @property
    def HELIUS_RPC(self):
        return f"https://mainnet.helius-rpc.com/?api-key={self.HELIUS_API_KEY}"

    @property
    def HELIUS_WSS(self):
        return f"wss://mainnet.helius-rpc.com/?api-key={self.HELIUS_API_KEY}"

    def validate(self):
        missing = [k for k in ["TELEGRAM_TOKEN","GROQ_API_KEY","HELIUS_API_KEY"] if not getattr(self, k)]
        if missing:
            raise ValueError(f"❌ Manquant : {', '.join(missing)}")
