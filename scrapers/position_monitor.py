import asyncio
import logging
from telegram import Bot
from utils.storage import Storage
from utils.solana import get_token_info
from handlers.demo_trading import close_demo_position, TAKE_PROFIT_PCT, STOP_LOSS_PCT
from config import Config

logger = logging.getLogger(__name__)


class PositionMonitor:
    def __init__(self, config: Config, storage: Storage, bot: Bot):
        self.config = config
        self.storage = storage
        self.bot = bot

    async def run(self):
        logger.info("📡 Position monitor démarré (TP/SL actifs)")
        while True:
            try:
                await self._check_all_positions()
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
            await asyncio.sleep(45)

    async def _check_all_positions(self):
        flat = self.storage.get_all_open_positions_flat()
        if not flat:
            return
        await asyncio.gather(*[self._check_position(chat_id, p) for chat_id, p in flat], return_exceptions=True)

    async def _check_position(self, chat_id, position):
        mint = position.get("mint")
        entry_price = position.get("entry_price", 0)
        if not mint or entry_price <= 0:
            return

        info = await get_token_info(mint)
        if not info or not info.get("price_usd"):
            return

        current_price = float(info["price_usd"])
        change_pct = ((current_price - entry_price) / entry_price) * 100

        if change_pct >= TAKE_PROFIT_PCT:
            await close_demo_position(self.bot, chat_id, position, current_price, "Take Profit 🎯")
        elif change_pct <= STOP_LOSS_PCT:
            await close_demo_position(self.bot, chat_id, position, current_price, "Stop Loss 🛑")
