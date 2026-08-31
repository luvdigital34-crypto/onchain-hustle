import asyncio
import time
import logging
import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from utils.storage import Storage
from utils.solana import get_new_tokens_pump, get_token_info, get_top_holder_pct, get_pump_token_creator
from handlers.demo_trading import is_demo_active, execute_demo_trade, is_daily_trading_paused, get_required_score
from scrapers.blockchain_listener import BlockchainListener
from ai.groq_client import GroqClient
from config import Config

logger = logging.getLogger(__name__)

MIN_LIQUIDITY_USD = 3000.0
MIN_MCAP_GROWTH_PCT = 30.0
MIN_BUYS_H1 = 15

SCORE_THRESHOLD = 50

WATCH_DURATION_SEC = 600
WATCHLIST_CHECK_INTERVAL_SEC = 15
NEW_TOKENS_SCAN_INTERVAL_SEC = 60
DEV_CHECK_INTERVAL_SEC = 60


async def get_tokens_created_by(address, limit=10):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://frontend-api.pump.fun/coins/user-created-coins/{address}",
                             params={"limit": limit, "offset": 0})
            if r.status_code != 200:
                return []
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_tokens_created_by error: {e}")
        return []


def compute_signal_score(info, growth_pct, dev_pct, dev_history, storage: Storage):
    score = 0
    breakdown = []
    signal_names = []

    liquidity = float(info.get("liquidity", 0) or 0)
    volume = float(info.get("volume_24h", 0) or 0)
    buys = info.get("buys_h1", 0)
    sells = info.get("sells_h1", 0)

    def add(base_points, name, label):
        w = storage.get_signal_weight_multiplier(name)
        pts = round(base_points * w)
        breakdown.append(f"{label} (+{pts})")
        signal_names.append(name)
        return pts

    if dev_pct >= 70:
        score += add(20, "dev_holding_high", f"Dev holding {dev_pct:.0f}%")
    elif dev_pct >= 40:
        score += add(10, "dev_holding_mid", f"Dev holding {dev_pct:.0f}%")

    if liquidity > 0:
        vol_liq_ratio = volume / liquidity
        if vol_liq_ratio >= 3:
            score += add(25, "vol_liq_high", f"Volume/Liquidité x{vol_liq_ratio:.1f}")
        elif vol_liq_ratio >= 1.5:
            score += add(15, "vol_liq_mid", f"Volume/Liquidité x{vol_liq_ratio:.1f}")

    total_txns = buys + sells
    if total_txns >= 10:
        buy_ratio = buys / total_txns if total_txns > 0 else 0
        if buy_ratio >= 0.65:
            score += add(20, "buy_pressure_high", f"Achats {buy_ratio*100:.0f}% des trades")
        elif buy_ratio >= 0.55:
            score += add(10, "buy_pressure_mid", f"Achats {buy_ratio*100:.0f}% des trades")

    if buys >= 50:
        score += add(15, "high_buy_count", f"{buys} achats en 1h — forte visibilité")
    elif buys >= MIN_BUYS_H1:
        score += add(8, "mid_buy_count", f"{buys} achats en 1h")

    if growth_pct >= 80:
        score += add(30, "growth_high", f"Croissance +{growth_pct:.0f}%")
    elif growth_pct >= 50:
        score += add(20, "growth_mid", f"Croissance +{growth_pct:.0f}%")
    elif growth_pct >= MIN_MCAP_GROWTH_PCT:
        score += add(10, "growth_low", f"Croissance +{growth_pct:.0f}%")

    if dev_history and dev_history.get("launched", 0) >= 2:
        rugged = dev_history.get("rugged", 0)
        good = dev_history.get("good", 0)
        launched = dev_history["launched"]
        rug_rate = rugged / launched if launched > 0 else 0
        if rug_rate >= 0.5:
            score -= 20
            breakdown.append(f"⚠️ Dev a rug {rugged}/{launched} tokens précédents (-20)")
        elif good >= 2:
            score += add(15, "dev_good_history", f"Dev a un bon historique ({good} bons tokens)")

    return max(0, min(score, 100)), breakdown, signal_names


class DevTracker:
    def __init__(self, config: Config, storage: Storage, bot: Bot):
        self.config = config
        self.storage = storage
        self.bot = bot
        self.groq = GroqClient(config.GROQ_API_KEY)
        self.seen_global = set()
        self.seen_by_wallet = {}
        self.watching = {}
        self.alerted = set()
        self.listener = BlockchainListener(config, self._on_realtime_mint)

    async def run(self):
        logger.info("🛠️ Dev tracker démarré (historique dev + poids adaptatifs + temps réel + limites quotidiennes)")
        await self._seed()
        await asyncio.gather(
            self._loop_tracked_devs(),
            self._loop_global_new_tokens(),
            self._loop_watchlist(),
            self.listener.run(),
        )

    async def _seed(self):
        tokens = await get_new_tokens_pump(50)
        for t in tokens:
            self.seen_global.add(t.get("tokenAddress", ""))
        for w in self.storage.get_dev_wallets():
            created = await get_tokens_created_by(w["address"])
            self.seen_by_wallet[w["address"]] = {c.get("mint", "") for c in created}

    async def _on_realtime_mint(self, mint):
        if mint in self.seen_global or mint in self.watching:
            return
        self.seen_global.add(mint)
        info = await get_token_info(mint)
        if not info:
            self.watching[mint] = {"first_mcap": 0, "started_at": time.time(), "checks": 0, "pending_mcap": True}
            return
        mcap = float(info.get("market_cap", 0) or 0)
        self.watching[mint] = {"first_mcap": mcap, "started_at": time.time(), "checks": 0, "pending_mcap": False}
        logger.info(f"⚡ Observation temps réel démarrée pour {mint}")

    async def _loop_tracked_devs(self):
        while True:
            try:
                await self._check_tracked_devs()
            except Exception as e:
                logger.error(f"Tracked devs loop error: {e}")
            await asyncio.sleep(DEV_CHECK_INTERVAL_SEC)

    async def _check_tracked_devs(self):
        wallets = self.storage.get_dev_wallets()
        if not wallets:
            return
        await asyncio.gather(*[self._check_dev_wallet(w) for w in wallets], return_exceptions=True)

    async def _check_dev_wallet(self, wallet):
        address = wallet["address"]
        label = wallet.get("label", address[:8])
        created = await get_tokens_created_by(address)
        if not created:
            return
        already = self.seen_by_wallet.get(address, set())
        for c in created:
            mint = c.get("mint", "")
            if not mint or mint in already:
                continue
            already.add(mint)
            self.seen_by_wallet[address] = already
            await self._notify_dev_deploy(label, address, mint)

    async def _notify_dev_deploy(self, label, dev_address, mint):
        info = await get_token_info(mint)
        name = info.get("name", "Unknown") if info else "Unknown"
        symbol = info.get("symbol", "") if info else ""
        mcap = float(info.get("market_cap", 0) or 0) if info else 0

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Trader sur Axiom", url=f"https://axiom.trade/meme/{mint}")],
            [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}")],
        ])

        msg = (
            f"🚨 *Dev tracké vient de déployer !*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Dev : *{label}*\n"
            f"🪙 *{name}* (${symbol})\n"
            f"🏦 MCap : ${mcap:,.0f}\n"
            f"🔗 `{mint}`"
        )

        for chat_id in self.storage.get_chat_ids():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode="Markdown",
                    reply_markup=keyboard, disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Dev deploy notify {chat_id}: {e}")

    async def _loop_global_new_tokens(self):
        while True:
            try:
                await self._check_global_new_tokens()
            except Exception as e:
                logger.error(f"Global new tokens loop error: {e}")
            await asyncio.sleep(NEW_TOKENS_SCAN_INTERVAL_SEC)

    async def _check_global_new_tokens(self):
        tokens = await get_new_tokens_pump(50)
        for token in tokens:
            mint = token.get("tokenAddress", "")
            if not mint or mint in self.seen_global:
                continue
            self.seen_global.add(mint)
            info = await get_token_info(mint)
            if not info:
                continue
            mcap = float(info.get("market_cap", 0) or 0)
            if mcap <= 0:
                continue
            self.watching[mint] = {
                "first_mcap": mcap,
                "started_at": time.time(),
                "checks": 0,
                "pending_mcap": False,
            }
            logger.info(f"👁️ Observation démarrée (fallback) pour {mint} (mcap initial: ${mcap:,.0f})")

    async def _loop_watchlist(self):
        while True:
            try:
                await self._check_watchlist()
            except Exception as e:
                logger.error(f"Watchlist loop error: {e}")
            await asyncio.sleep(WATCHLIST_CHECK_INTERVAL_SEC)

    async def _check_watchlist(self):
        now = time.time()
        to_remove = []

        for mint, watch in list(self.watching.items()):
            elapsed = now - watch["started_at"]
            if elapsed > WATCH_DURATION_SEC:
                to_remove.append(mint)
                continue

            info = await get_token_info(mint)
            if not info:
                continue

            current_mcap = float(info.get("market_cap", 0) or 0)

            if watch.get("pending_mcap") and current_mcap > 0:
                watch["first_mcap"] = current_mcap
                watch["pending_mcap"] = False
                continue

            watch["checks"] += 1
            first_mcap = watch["first_mcap"]
            if first_mcap <= 0:
                continue

            growth_pct = ((current_mcap - first_mcap) / first_mcap) * 100
            liquidity = float(info.get("liquidity", 0) or 0)

            if growth_pct < MIN_MCAP_GROWTH_PCT or liquidity < MIN_LIQUIDITY_USD:
                continue
            if mint in self.alerted:
                continue

            dev_pct = await get_top_holder_pct(mint, self.config.HELIUS_RPC)
            creator = await get_pump_token_creator(mint)
            dev_history = self.storage.get_dev_history(creator) if creator else None

            score, breakdown, signal_names = compute_signal_score(
                info, growth_pct, dev_pct, dev_history=dev_history, storage=self.storage
            )

            if score >= SCORE_THRESHOLD:
                self.alerted.add(mint)
                to_remove.append(mint)
                age_sec = int(elapsed)
                await self._notify_real_signal(mint, info, growth_pct, dev_pct, score, breakdown, age_sec, signal_names, creator)

        for mint in to_remove:
            self.watching.pop(mint, None)

    async def _notify_real_signal(self, mint, info, growth_pct, dev_pct, score, breakdown, age_sec, signal_names, creator):
        name = info.get("name", "Unknown")
        symbol = info.get("symbol", "")
        price = float(info.get("price_usd", 0) or 0)
        mcap = float(info.get("market_cap", 0) or 0)
        vol = float(info.get("volume_24h", 0) or 0)
        liq = float(info.get("liquidity", 0) or 0)

        if age_sec < 60:
            age_str = f"{age_sec}s"
        else:
            age_str = f"{age_sec // 60}min{age_sec % 60:02d}s"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Trader sur Axiom", url=f"https://axiom.trade/meme/{mint}")],
            [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}")],
        ])

        signals_text = "\n".join(f"✓ {b}" for b in breakdown) if breakdown else "_(aucun bonus, juste les filtres de base)_"

        msg = (
            f"🔥 *Signaux réels détectés !* (⏱️ {age_str} après détection)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *{name}* (${symbol})\n"
            f"💰 Prix : ${price:.8f}\n"
            f"🏦 MCap : ${mcap:,.0f}\n"
            f"📈 Croissance MCap : +{growth_pct:.0f}%\n"
            f"📊 Volume : ${vol:,.0f}\n"
            f"💧 Liquidité : ${liq:,.0f}\n\n"
            f"🎯 *Score : {score}/100*\n{signals_text}\n\n"
            f"🔗 `{mint}`"
        )

        for chat_id in self.storage.get_chat_ids():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode="Markdown",
                    reply_markup=keyboard, disable_web_page_preview=True
                )
                if not is_demo_active(str(chat_id)):
                    continue
                if is_daily_trading_paused(str(chat_id), self.storage, self.config):
                    continue  # gain quotidien cible atteint, pas de nouveau trade
                required = get_required_score(str(chat_id), self.storage, self.config, base_threshold=SCORE_THRESHOLD)
                if score < required:
                    continue  # pas assez fort vu la perte du jour, on devient plus sélectif
                await execute_demo_trade(
                    bot=self.bot, chat_id=str(chat_id),
                    token_name=name, mint=mint,
                    action="buy", confidence=score,
                    reason=f"Score {score}/100 en {age_str} — " + ", ".join(breakdown[:2]),
                    signal_names=signal_names,
                    creator=creator,
                )
            except Exception as e:
                logger.error(f"Real signal notify {chat_id}: {e}")
