import asyncio
import logging
from telegram import Bot
from utils.storage import Storage
from utils.solana import get_wallet_txs, get_token_info
from handlers.trading import alert_keyboard
from handlers.demo_trading import is_demo_active, execute_demo_trade
from config import Config

logger = logging.getLogger(__name__)

class WalletTracker:
    def __init__(self, config: Config, storage: Storage, bot: Bot):
        self.config = config
        self.storage = storage
        self.bot = bot
        self.last_sigs = {}

    async def run(self):
        logger.info("👀 Wallet tracker démarré")
        await self._seed()
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.error(f"Wallet tracker error: {e}")
            await asyncio.sleep(self.config.WALLET_INTERVAL)

    async def _seed(self):
        for w in self.storage.get_wallets():
            txs = await get_wallet_txs(w["address"], self.config.HELIUS_RPC, 1)
            if txs:
                self.last_sigs[w["address"]] = txs[0].get("signature", "")

    async def _check_all(self):
        wallets = self.storage.get_wallets()
        if not wallets:
            return
        await asyncio.gather(*[self._check(w) for w in wallets], return_exceptions=True)

    async def _check(self, wallet):
        address = wallet["address"]
        label = wallet.get("label", address[:8])
        try:
            txs = await get_wallet_txs(address, self.config.HELIUS_RPC, 5)
            if not txs:
                return
            latest = txs[0].get("signature", "")
            last = self.last_sigs.get(address, "")
            if latest == last:
                return
            self.last_sigs[address] = latest
            new_txs = []
            for tx in txs:
                if tx.get("signature") == last:
                    break
                new_txs.append(tx)
            for tx in new_txs:
                await self._notify(label, address, tx)
        except Exception as e:
            logger.error(f"Check wallet {address}: {e}")

    async def _notify(self, label, address, tx):
        sig = tx.get("signature", "")
        status = "✅" if not tx.get("err") else "❌"
        solscan = f"https://solscan.io/tx/{sig}"
        gmgn = f"https://gmgn.ai/sol/account/{address}"

        msg = (
            f"👀 *Trade détecté — {label}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status} Nouvelle transaction\n"
            f"🔗 [Solscan]({solscan}) | [GMGN]({gmgn})\n\n"
            f"💡 *Tu veux copier ce trade ?*"
        )

        from handlers.trading import alert_keyboard
        keyboard = alert_keyboard(address)

        for chat_id in self.storage.get_chat_ids():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
                if is_demo_active(str(chat_id)):
                    await execute_demo_trade(
                        bot=self.bot, chat_id=str(chat_id),
                        token_name="CopyTrade", mint=address,
                        action="buy", confidence=70,
                        reason=f"Copytrade de {label}"
                    )
            except Exception as e:
                logger.error(f"Notify error {chat_id}: {e}")
