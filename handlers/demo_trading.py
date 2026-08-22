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


async def demo_start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    demo_active.add(chat_id)
    portfolio = storage.get_demo_portfolio(chat_id)
    await update.message.reply_text(
        f"🤖 *IA Trading Démo — Activé !*\n\n"
        f"💰 Portfolio : *{portfolio['sol']:.2f} SOL*\n"
        f"📊 Trades : *{portfolio['trades']}*\n"
        f"📈 PnL : *{portfolio['pnl']:+.4f} SOL*\n\n"
        f"L'IA achète sur de vrais signaux et gère chaque position :\n"
        f"🎯 Take Profit : +{TAKE_PROFIT_PCT:.0f}%\n"
        f"🛑 Stop Loss : {STOP_LOSS_PCT:.0f}%\n\n"
        f"🔔 Notification à chaque achat et vente !\n\n"
        f"Tape /demo_status pour voir les perfs\n"
        f"Tape /demo_stop pour arrêter",
        parse_mode="Markdown"
    )

async def demo_status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    portfolio = storage.get_demo_portfolio(chat_id)
    positions = storage.get_open_positions(chat_id)
    trades = [t for t in storage.get_demo_trades() if t.get("chat_id") == chat_id][-10:]
    pnl = portfolio.get("pnl", 0)

    msg = (
        f"📊 *IA Trading Démo*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 SOL dispo : *{portfolio.get('sol',10):.4f}*\n"
        f"{'📈' if pnl>=0 else '📉'} PnL réalisé : *{pnl:+.4f} SOL*\n"
        f"🔄 Trades : *{portfolio.get('trades',0)}*\n"
        f"🤖 Statut : *{'🟢 Actif' if chat_id in demo_active else '🔴 Inactif'}*\n"
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

    if trades:
        msg += "\n📋 *Derniers trades :*\n"
        for t in reversed(trades):
            e = "🟢" if t.get("action")=="buy" else "🔴"
            pnl_t = t.get("pnl", 0)
            pnl_str = f" ({pnl_t:+.4f} SOL)" if t.get("action") == "sell" else ""
            msg += f"{e} {t.get('action','').upper()} {t.get('token','')}{pnl_str}\n"

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


async def execute_demo_trade(bot, chat_id, token_name, mint, action, confidence, reason):
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

    change_pct = ((current_price - entry_price) / entry_price) * 100
    exit_amount = amount_sol * (1 + change_pct / 100)
    pnl_trade = exit_amount - amount_sol

    portfolio = storage.get_demo_portfolio(chat_id)
    portfolio["sol"] = portfolio.get("sol", 10.0) + exit_amount
    portfolio["pnl"] = portfolio.get("pnl", 0) + pnl_trade
    storage.save_demo_portfolio(chat_id, portfolio)
    storage.remove_open_position(chat_id, mint)

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
