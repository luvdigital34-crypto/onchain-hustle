import asyncio
import logging
import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from utils.storage import Storage
from ai.groq_client import GroqClient
from handlers.demo_trading import is_demo_active, execute_demo_trade
from config import Config

logger = logging.getLogger(__name__)

REDDIT_SUBS = ["CryptoMoonShots", "solana", "SolanaMemeCoins", "CryptoCurrency"]

class TrendHunter:
    def __init__(self, config: Config, storage: Storage, bot: Bot):
        self.config = config
        self.storage = storage
        self.bot = bot
        self.groq = GroqClient(config.GROQ_API_KEY)
        self.seen = set()

    async def run(self):
        logger.info("🔍 Trend Hunter démarré")
        while True:
            try:
                await asyncio.gather(
                    self._scan_google_trends(),
                    self._scan_crypto_news(),
                    self._scan_reddit(),
                )
            except Exception as e:
                logger.error(f"Trend hunter error: {e}")
            await asyncio.sleep(self.config.TREND_INTERVAL)

    async def _scan_google_trends(self):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get("https://trends.google.com/trending/rss?geo=US", headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200: return
                import re
                titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
                titles = [t for t in titles if t and "Google Trends" not in t][:10]
                for title in titles:
                    tid = f"google_{title[:30]}"
                    if tid in self.seen: continue
                    analysis = await self.groq.analyze_trend(title, "Google Trends")
                    if analysis.get("score", 0) >= 7 and analysis.get("token_opportunity"):
                        self.seen.add(tid)
                        await self._notify(title, "Google Trends 🔍", analysis)
        except Exception as e:
            logger.error(f"Google trends error: {e}")

    async def _scan_crypto_news(self):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get("https://cryptonews.com/news/feed/", headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200: return
                import re
                titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)[:10]
                for title in titles:
                    tid = f"news_{title[:30]}"
                    if tid in self.seen: continue
                    analysis = await self.groq.analyze_trend(title, "Crypto News")
                    if analysis.get("score", 0) >= 7:
                        self.seen.add(tid)
                        await self._notify(title, "Crypto News 📰", analysis)
        except Exception as e:
            logger.error(f"Crypto news error: {e}")

    async def _scan_reddit(self):
        for sub in REDDIT_SUBS:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(
                        f"https://www.reddit.com/r/{sub}/hot.json",
                        params={"limit": 10},
                        headers={"User-Agent": "OnChainHunterBot/1.0"}
                    )
                    if r.status_code != 200:
                        continue
                    posts = r.json().get("data", {}).get("children", [])
                    for p in posts:
                        data = p.get("data", {})
                        title = data.get("title", "")
                        score = data.get("score", 0)
                        if not title or score < 50:
                            continue
                        tid = f"reddit_{title[:30]}"
                        if tid in self.seen:
                            continue
                        analysis = await self.groq.analyze_trend(
                            f"{title} (👍{score} sur r/{sub})", f"Reddit r/{sub}"
                        )
                        if analysis.get("score", 0) >= 7:
                            self.seen.add(tid)
                            await self._notify(title, f"Reddit r/{sub} 👽", analysis)
            except Exception as e:
                logger.error(f"Reddit scan error ({sub}): {e}")

    async def _notify(self, content, source, analysis):
        score = analysis.get("score", 5)
        summary = analysis.get("summary", content[:100])
        urgency = analysis.get("urgency", "low")
        trend_type = analysis.get("type", "trend")
        urgency_emoji = "🔴 URGENT" if urgency == "high" else "🟡 Modéré" if urgency == "medium" else "🟢 Normal"
        type_emoji = {"meme": "😂", "narrative": "📖", "trend": "📈", "news": "📰"}.get(trend_type, "🔥")

        token_idea = await self.groq.generate_token_idea(content, source, "trend")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Créer ce token", url="https://pump.fun/create"),
             InlineKeyboardButton("🔍 Rechercher", url=f"https://www.google.com/search?q={content[:20].replace(' ','+')}+meme+coin")],
        ])

        msg = (
            f"🔥 *Nouvelle Tendance !*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{type_emoji} *Type :* {trend_type.capitalize()}\n"
            f"📡 *Source :* {source}\n"
            f"⚡ *Urgence :* {urgency_emoji}\n"
            f"🎯 *Score :* {score}/10\n\n"
            f"📋 *Tendance :*\n_{summary}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *Opportunité Meme Coin :*\n{token_idea}"
        )

        for chat_id in self.storage.get_chat_ids():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
                if is_demo_active(str(chat_id)) and score >= 8:
                    await execute_demo_trade(
                        bot=self.bot, chat_id=str(chat_id),
                        token_name=f"Trend: {summary[:20]}",
                        mint="trend_"+content[:10].replace(" ","_"),
                        action="buy", confidence=score*10,
                        reason=f"Tendance {trend_type} score {score}/10"
                    )
            except Exception as e:
                logger.error(f"Trend notify {chat_id}: {e}")
