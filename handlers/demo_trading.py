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

async def demo_start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    demo_active.add(chat_id)
    portfolio = storage.get_demo_portfolio(chat_id)
    await update.message.reply_text(
        f"🤖 *IA Trading Démo — Activé !*\n\n"
        f"💰 Portfolio : *{portfolio['sol']:.2f} SOL*\n"
        f"📊 Trades : *{portfolio['trades']}*\n"
        f"📈 PnL : *{portfolio['pnl']:+.4f} SOL*\n\n"
        f"L'IA analyse et trade automatiquement.\n"
        f"🔔 Notification à chaque trade !\n\n"
        f"_`/demo_status` pour les perfs_\n_`/demo_stop` pour arrêter_",
        parse_mode="Markdown"
    )

async def demo_status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    portfolio = storage.get_demo_portfolio(chat_id)
    trades = [t for t in storage.get_demo_trades() if t.get("chat_id") == chat_id][-10:]
    pnl = portfolio.get("pnl", 0)
    msg = (
        f"📊 *IA Trading Démo*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 SOL : *{portfolio.get('sol',10):.4f}*\n"
        f"{'📈' if pnl>=0 else '📉'} PnL : *{pnl:+.4f} SOL*\n"
        f"🔄 Trades : *{portfolio.get('trades',0)}*\n"
        f"🤖 Statut : *{'🟢 Actif' if chat_id in demo_active else '🔴 Inactif'}*\n"
    )
    if trades:
        msg += "\n📋 *Derniers trades :*\n"
        for t in reversed(trades):
            e = "🟢" if t.get("action")=="buy" else "🔴"
            msg += f"{e} {t.get('action','').upper()} {t.get('token','')} — {t.get('amount',0):.3f} SOL\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def demo_stop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    demo_active.discard(chat_id)
    portfolio = storage.get_demo_portfolio(chat_id)
    await update.message.reply_text(
        f"⏹️ *Démo arrêté*\n\n"
        f"💰 SOL final : *{portfolio.get('sol',10):.4f}*\n"
        f"📈 PnL : *{portfolio.get('pnl',0):+.4f} SOL*\n"
        f"🔄 Trades : *{portfolio.get('trades',0)}*",
        parse_mode="Markdown"
    )

def is_demo_active(chat_id): return str(chat_id) in demo_active

async def execute_demo_trade(bot, chat_id, token_name, mint, action, confidence, reason):
    portfolio = storage.get_demo_portfolio(chat_id)
    sol = portfolio.get("sol", 10.0)
    amount = sol * 0.15
    pnl_trade = amount * 0.1 if action == "sell" else 0
    if action == "buy": portfolio["sol"] -= amount
    else: portfolio["sol"] += amount + pnl_trade
    portfolio["trades"] = portfolio.get("trades", 0) + 1
    portfolio["pnl"] = portfolio.get("pnl", 0) + pnl_trade
    storage.save_demo_portfolio(chat_id, portfolio)
    storage.add_demo_trade({"chat_id": chat_id, "action": action, "token": token_name, "mint": mint, "amount": amount, "pnl": pnl_trade, "confidence": confidence, "reason": reason})
    emoji = "🟢" if action == "buy" else "🔴"
    msg = (
        f"🤖 *IA Demo Trade !*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} *{action.upper()}* — {token_name}\n"
        f"💰 Montant : {amount:.3f} SOL\n"
        f"🎯 Confiance : {confidence}%\n"
        f"💡 _{reason}_\n\n"
        f"📊 Portfolio : {portfolio['sol']:.4f} SOL\n"
        f"📈 PnL total : {portfolio['pnl']:+.4f} SOL\n\n"
        f"[Chart](https://dexscreener.com/solana/{mint}) | [Terminal](https://gmgn.ai/sol/token/{mint})"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Demo trade error: {e}")
