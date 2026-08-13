import asyncio
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from utils.storage import Storage
from utils.solana import get_new_tokens_pump, get_token_info
from handlers.demo_trading import is_demo_active, execute_demo_trade
from ai.groq_client import GroqClient
from config import Config

logger = logging.getLogger(__name__)

class DevTracker:
    def __init__(self, config: Config, storage: Storage, bot: Bot):
        self.config = config
        self.storage = storage
        self.bot = bot
        self.groq = GroqClient(config.GROQ_API_KEY)
        self.seen = set()

    async def run(self):
        logger.info("🛠️ Dev tracker démarré")
        await self._seed()
        while True:
            try:
                await self._check()
            except Exception as e:
                logger.error(f"Dev tracker error: {e}")
            await asyncio.sleep(120)

    async def _seed(self):
        tokens = await get_new_tokens_pump(20)
        for t in tokens:
            self.seen.add(t.get("tokenAddress", ""))

    async def _check(self):
        tokens = await get_new_tokens_pump(20)
        for token in tokens:
            mint = token.get("tokenAddress", "")
            if not mint or mint in self.seen:
                continue
            self.seen.add(mint)
            await self._notify(mint, token)

    async def _notify(self, mint, token_data):
        info = await get_token_info(mint)
        if not info:
            return

        name = info.get("name", "Unknown")
        symbol = info.get("symbol", "")
        price = float(info.get("price_usd", 0) or 0)
        mcap = float(info.get("market_cap", 0) or 0)
        vol = float(info.get("volume_24h", 0) or 0)
        liq = float(info.get("liquidity", 0) or 0)
        dex_url = info.get("dex_url", "")

        analysis = await self.groq.analyze_trend(
            f"Nouveau token: {name} (${symbol}) MCap: ${mcap:,.0f}", "pump.fun"
        )
        score = analysis.get("score", 5)
        urgency = analysis.get("urgency", "low")
        urgency_emoji = "🔴" if urgency == "high" else "🟡" if urgency == "medium" else "🟢"

        pump_url = f"https://pump.fun/{mint}"
        gmgn_url = f"https://gmgn.ai/sol/token/{mint}"

        msg = (
            f"🛠️ *Nouveau Token Deployé !*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *{name}* (${symbol})\n"
            f"💰 Prix : ${price:.8f}\n"
            f"🏦 MCap : ${mcap:,.0f}\n"
            f"📊 Volume : ${vol:,.0f}\n"
            f"💧 Liquidité : ${liq:,.0f}\n\n"
            f"🤖 *Score IA :* {score}/10 {urgency_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Tu veux acheter ?*"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Acheter !", callback_data=f"buy|{mint}|10"),
             InlineKeyboardButton("❌ Passer", callback_data=f"skip|{mint}|0")],
            [InlineKeyboardButton("📊 Chart", url=dex_url or pump_url),
             InlineKeyboardButton("⚡ Terminal", url=gmgn_url)],
        ])

        for chat_id in self.storage.get_chat_ids():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
                if is_demo_active(str(chat_id)) and score >= 7:
                    await execute_demo_trade(
                        bot=self.bot, chat_id=str(chat_id),
                        token_name=name, mint=mint,
                        action="buy", confidence=score*10,
                        reason=f"Nouveau token score {score}/10"
                    )
            except Exception as e:
                logger.error(f"Dev tracker notify {chat_id}: {e}")
