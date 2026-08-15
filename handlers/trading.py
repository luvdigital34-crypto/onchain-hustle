import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.storage import Storage
from utils.solana import get_token_info, get_jupiter_quote
from config import Config

logger = logging.getLogger(__name__)
config = Config()
storage = Storage(config.DATA_FILE)
SOL_MINT = "So11111111111111111111111111111111111111112"

def buy_sell_keyboard(mint, name=""):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Buy 10%", callback_data=f"buy|{mint}|10"),
         InlineKeyboardButton("🟢 Buy 25%", callback_data=f"buy|{mint}|25"),
         InlineKeyboardButton("🟢 Buy 40%", callback_data=f"buy|{mint}|40")],
        [InlineKeyboardButton("🟢 Buy 70%", callback_data=f"buy|{mint}|70"),
         InlineKeyboardButton("🟢 Buy 100%", callback_data=f"buy|{mint}|100")],
        [InlineKeyboardButton("🔴 Sell 10%", callback_data=f"sell|{mint}|10"),
         InlineKeyboardButton("🔴 Sell 25%", callback_data=f"sell|{mint}|25"),
         InlineKeyboardButton("🔴 Sell 40%", callback_data=f"sell|{mint}|40")],
        [InlineKeyboardButton("🔴 Sell 70%", callback_data=f"sell|{mint}|70"),
         InlineKeyboardButton("🔴 Sell 100%", callback_data=f"sell|{mint}|100")],
        [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}"),
         InlineKeyboardButton("⚡ Terminal", url=f"https://axiom.trade/meme/{mint}")],
    ]) 
    ])

def alert_keyboard(mint):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Acheter !", callback_data=f"buy|{mint}|10"),
         InlineKeyboardButton("❌ Passer", callback_data=f"skip|{mint}|0")],
        [InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}"),
         InlineKeyboardButton("⚡ Terminal", url=f"https://axiom.trade/meme/{mint}")],
    ])

async def buy_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage : `/buy TOKEN_ADDRESS`", parse_mode="Markdown")
        return
    mint = ctx.args[0].strip()
    await update.message.reply_text("⏳ Récupération des infos...")
    info = await get_token_info(mint)
    if not info:
        await update.message.reply_text("❌ Token introuvable.")
        return
    change = info.get("change_24h", 0)
    arrow = "📈" if float(change or 0) >= 0 else "📉"
    msg = (
        f"🛒 *{info.get('name')} (${info.get('symbol')})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Prix : ${float(info.get('price_usd',0)):.8f}\n"
        f"🏦 MCap : ${float(info.get('market_cap',0)):,.0f}\n"
        f"{arrow} 24h : {change}%\n\n"
        f"Choisis ton montant :"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=buy_sell_keyboard(mint))

async def sell_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage : `/sell TOKEN_ADDRESS`", parse_mode="Markdown")
        return
    mint = ctx.args[0].strip()
    info = await get_token_info(mint)
    name = info.get("name", "Token") if info else "Token"
    await update.message.reply_text(
        f"💸 *Vendre {name}*\nChoisis le % à vendre :",
        parse_mode="Markdown", reply_markup=buy_sell_keyboard(mint)
    )

async def trade_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    action, mint, pct = parts[0], parts[1], parts[2]

    if action == "skip":
        await query.edit_message_reply_markup(reply_markup=None)
        return

    jup_url = f"https://jup.ag/swap/{'SOL-'+mint if action=='buy' else mint+'-SOL'}"
    gmgn_url = f"https://gmgn.ai/sol/token/{mint}"
    emoji = "🟢 Achat" if action == "buy" else "🔴 Vente"

    await query.edit_message_text(
        f"{emoji} *{pct}%* demandé !\n\n"
        f"⚡ Exécute sur :\n"
        f"🔗 [Jupiter — Meilleur prix]({jup_url})\n"
        f"🔗 [GMGN Terminal]({gmgn_url})\n\n"
        f"_Connecte ton wallet Phantom_",
        parse_mode="Markdown", disable_web_page_preview=False
    )
