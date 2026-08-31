import time
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.storage import Storage
from ai.groq_client import GroqClient
from config import Config

logger = logging.getLogger(__name__)
config = Config()
storage = Storage(config.DATA_FILE)
groq = GroqClient(config.GROQ_API_KEY)
demo_active = set()

TAKE_PROFIT_PCT = 50.0
STOP_LOSS_PCT = -20.0
POSITION_SIZE_PCT = 0.15
SELECTIVE_SCORE_THRESHOLD = 80  # seuil relevé quand le bot est en grosse perte du jour


async def demo_start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    demo_active.add(chat_id)
    portfolio = storage.get_demo_portfolio(chat_id)
    await update.message.reply_text(
        f"🤖 *IA Trading Démo — Activé !*\n\n"
        f"💰 Portfolio : *{portfolio['sol']:.2f} SOL*\n"
        f"📊 Trades : *{portfolio['trades']}*\n"
        f"📈 PnL : *{portfolio['pnl']:+.4f} SOL*\n\n"
        f"L'IA gère chaque position avec :\n"
        f"🎯 Take Profit : +{TAKE_PROFIT_PCT:.0f}%\n"
        f"🛑 Stop Loss : {STOP_LOSS_PCT:.0f}%\n"
        f"🟢 Gain quotidien cible : +{config.DAILY_PROFIT_TARGET:.1f} SOL (pause si atteint)\n"
        f"🔴 Perte quotidienne limite : -{config.DAILY_LOSS_LIMIT:.1f} SOL (devient très sélectif)\n\n"
        f"Tape `/demo_status` pour voir les perfs\n"
        f"Tape `/demo_stop` pour arrêter",
        parse_mode="Markdown"
    )

async def demo_status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    portfolio = storage.get_demo_portfolio(chat_id)
    positions = storage.get_open_positions(chat_id)
    today = storage.get_today_stats(chat_id)
    trades = [t for t in storage.get_demo_trades() if t.get("chat_id") == chat_id]
    sells = [t for t in trades if t.get("action") == "sell"]
    pnl = portfolio.get("pnl", 0)

    total_wins = sum(1 for t in sells if t.get("pnl", 0) > 0)
    total_losses = sum(1 for t in sells if t.get("pnl", 0) <= 0)
    total_tp = sum(1 for t in sells if "Take Profit" in t.get("reason", ""))
    total_sl = sum(1 for t in sells if "Stop Loss" in t.get("reason", ""))
    win_rate = (total_wins / len(sells) * 100) if sells else 0
    avg_win = sum(t["pnl"] for t in sells if t.get("pnl", 0) > 0) / total_wins if total_wins else 0
    avg_loss = sum(t["pnl"] for t in sells if t.get("pnl", 0) <= 0) / total_losses if total_losses else 0

    msg = (
        f"📊 *IA Trading Démo — Statut complet*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 SOL dispo : *{portfolio.get('sol',10):.4f}*\n"
        f"{'📈' if pnl>=0 else '📉'} PnL total réalisé : *{pnl:+.4f} SOL*\n"
        f"🔄 Trades totaux : *{portfolio.get('trades',0)}*\n"
        f"🤖 Statut : *{'🟢 Actif' if chat_id in demo_active else '🔴 Inactif'}*\n\n"
        f"📆 *Aujourd'hui :*\n"
        f"{'📈' if today['pnl']>=0 else '📉'} PnL du jour : *{today['pnl']:+.4f} SOL*\n"
        f"🎯 Take Profits : *{today['tp']}*\n"
        f"🛑 Stop Loss : *{today['sl']}*\n\n"
        f"📈 *Historique global des ventes :*\n"
        f"✅ Gagnants : *{total_wins}* | ❌ Perdants : *{total_losses}*\n"
        f"🎯 Win rate : *{win_rate:.0f}%*\n"
        f"🎯 Total TP : *{total_tp}* | 🛑 Total SL : *{total_sl}*\n"
        f"💚 Gain moyen/trade gagnant : *{avg_win:+.4f} SOL*\n"
        f"💔 Perte moyenne/trade perdant : *{avg_loss:+.4f} SOL*\n"
    )

    if positions:
        msg += f"\n📂 *Positions ouvertes ({len(positions)}) :*\n"
        from utils.solana import get_token_info
        for p in positions:
            info = await get_token_info(p["mint"])
            if info and info.get("price_usd", 0) > 0:
                current_price = float(info["price_usd"])
                change = ((current_price - p["entry_price"]) / p["entry_price"]) * 100
                emoji = "🟢" if change >= 0 else "🔴"
                msg += f"{emoji} {p['name']} — {change:+.1f}% depuis l'achat\n"
            else:
                msg += f"⚪ {p['name']} — prix indisponible\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def demo_stop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    demo_active.discard(chat_id)
    portfolio = storage.get_demo_portfolio(chat_id)
    await update.message.reply_text(
        f"⏹️ *Démo arrêté*\n\n"
        f"💰 SOL final : *{portfolio.get('sol',10):.4f}*\n"
        f"📈 PnL : *{portfolio.get('pnl',0):+.4f} SOL*\n"
        f"🔄 Trades : *{portfolio.get('trades',0)}*\n\n"
        f"_Les positions ouvertes restent surveillées, mais aucun nouvel achat ne sera fait._",
        parse_mode="Markdown"
    )

def is_demo_active(chat_id): return str(chat_id) in demo_active


def is_daily_trading_paused(chat_id, storage_ref: Storage, config_ref: Config):
    """True si le gain quotidien cible est atteint (pause totale des nouveaux achats)."""
    today = storage_ref.get_today_stats(chat_id)
    return today["pnl"] >= config_ref.DAILY_PROFIT_TARGET


def get_required_score(chat_id, storage_ref: Storage, config_ref: Config, base_threshold=50):
    """Relève le seuil de score requis si la perte du jour dépasse la limite (plus sélectif, pas d'arrêt total)."""
    today = storage_ref.get_today_stats(chat_id)
    if today["pnl"] <= -config_ref.DAILY_LOSS_LIMIT:
        return SELECTIVE_SCORE_THRESHOLD
    return base_threshold


async def execute_demo_trade(bot, chat_id, token_name, mint, action, confidence, reason, signal_names=None, creator=None):
    from utils.solana import get_token_info

    info = await get_token_info(mint)
    if not info or not info.get("price_usd"):
        logger.warning(f"Impossible de récupérer le prix pour {mint}, trade annulé")
        return

    entry_price = float(info["price_usd"])
    portfolio = storage.get_demo_portfolio(chat_id)
    sol = portfolio.get("sol", 10.0)
    amount = sol * POSITION_SIZE_PCT

    if amount <= 0 or sol < amount:
        return

    portfolio["sol"] -= amount
    portfolio["trades"] = portfolio.get("trades", 0) + 1
    storage.save_demo_portfolio(chat_id, portfolio)

    storage.add_open_position(chat_id, {
        "mint": mint,
        "name": token_name,
        "entry_price": entry_price,
        "amount_sol": amount,
        "opened_at": time.time(),
        "reason": reason,
        "signal_names": signal_names or [],
        "creator": creator,
    })

    storage.add_demo_trade({
        "chat_id": chat_id, "action": "buy", "token": token_name, "mint": mint,
        "amount": amount, "pnl": 0, "confidence": confidence, "reason": reason
    })

    msg = (
        f"🤖 *IA Demo — Achat !*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 *BUY* — {token_name}\n"
        f"💰 Montant : {amount:.3f} SOL\n"
        f"💵 Prix d'entrée : ${entry_price:.8f}\n"
        f"🎯 Confiance : {confidence}%\n"
        f"💡 _{reason}_\n\n"
        f"📊 Portfolio : {portfolio['sol']:.4f} SOL\n\n"
        f"🎯 TP: +{TAKE_PROFIT_PCT:.0f}% | 🛑 SL: {STOP_LOSS_PCT:.0f}%"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Demo trade notify error: {e}")


async def close_demo_position(bot, chat_id, position, current_price, reason_label):
    entry_price = position["entry_price"]
    amount_sol = position["amount_sol"]
    mint = position["mint"]
    name = position["name"]
    signal_names = position.get("signal_names", [])
    creator = position.get("creator")

    change_pct = ((current_price - entry_price) / entry_price) * 100
    exit_amount = amount_sol * (1 + change_pct / 100)
    pnl_trade = exit_amount - amount_sol
    won = pnl_trade > 0
    is_tp = "Take Profit" in reason_label
    is_sl = "Stop Loss" in reason_label

    portfolio = storage.get_demo_portfolio(chat_id)
    portfolio["sol"] = portfolio.get("sol", 10.0) + exit_amount
    portfolio["pnl"] = portfolio.get("pnl", 0) + pnl_trade
    storage.save_demo_portfolio(chat_id, portfolio)
    storage.remove_open_position(chat_id, mint)
    storage.update_today_stats(chat_id, pnl_trade, is_tp=is_tp, is_sl=is_sl)

    if signal_names:
        storage.record_signal_result(signal_names, won)

    if creator:
        storage.record_dev_outcome(creator, "good" if is_tp else ("rugged" if is_sl else ("good" if won else "rugged")))

    storage.add_demo_trade({
        "chat_id": chat_id, "action": "sell", "token": name, "mint": mint,
        "amount": exit_amount, "pnl": pnl_trade, "confidence": 0,
        "reason": reason_label
    })

    emoji = "🎯" if pnl_trade >= 0 else "🛑"
    msg = (
        f"🤖 *IA Demo — Vente !*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} *SELL* — {name} ({reason_label})\n"
        f"📈 Résultat : {change_pct:+.1f}%\n"
        f"💰 PnL : {pnl_trade:+.4f} SOL\n\n"
        f"📊 Portfolio : {portfolio['sol']:.4f} SOL\n"
        f"📈 PnL total : {portfolio['pnl']:+.4f} SOL"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Demo close notify error: {e}")
