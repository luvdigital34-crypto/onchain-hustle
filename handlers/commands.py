import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.storage import Storage
from utils.solana import get_sol_balance
from config import Config

logger = logging.getLogger(__name__)
config = Config()
storage = Storage(config.DATA_FILE)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    storage.add_chat_id(str(update.effective_chat.id))
    await update.message.reply_text(
        "🔫 *OnChainHunter* — Bienvenue !\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛠️ *DEV TRACKER*\n"
        "`/trackdev ADRESSE NOM` — Tracker un dev\n"
        "`/devs` — Voir les devs trackés\n"
        "`/untrackdev ADRESSE` — Arrêter le tracking\n\n"
        "💰 *MON WALLET*\n"
        "`/wallet ADRESSE` — Connecter mon wallet\n"
        "`/balance` — Voir mon solde\n\n"
        "📊 *TRADING*\n"
        "`/buy TOKEN` — Acheter un token\n"
        "`/sell TOKEN` — Vendre un token\n\n"
        "🪙 *CRÉER UN TOKEN*\n"
        "`/create` — Créer depuis une image\n\n"
        "🤖 *IA TRADING DÉMO*\n"
        "`/demo` — Lancer le trading démo\n"
        "`/demo_status` — Voir les performances\n"
        "`/demo_stop` — Arrêter le démo\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 *Alertes auto :*\n"
        "• Quand un dev tracké déploie un token\n"
        "• Quand l'IA repère elle-même un bon dev sur pump.fun\n"
        "• Tendances détectées par l'IA",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Guide rapide*\n\n"
        "1️⃣ `/wallet TON_ADRESSE` — Connecte ton wallet\n"
        "2️⃣ `/trackdev ADRESSE Nom` — Tracker un dev\n"
        "3️⃣ `/demo` — Lance l'IA en mode démo\n"
        "4️⃣ `/create` — Envoie une image → génère un token\n\n"
        "💡 L'IA scanne aussi pump.fun toute seule et t'alerte quand elle repère un bon dev !",
        parse_mode="Markdown"
    )

async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    devs = storage.get_dev_wallets()
    chats = storage.get_chat_ids()
    await update.message.reply_text(
        f"⚡ *Statut — OnChainHunter 🔫*\n\n"
        f"🛠️ Devs trackés : {'🟢 ' + str(len(devs)) if devs else '🔴 Aucun'}\n"
        f"👥 Abonnés : {len(chats)}\n"
        f"🤖 IA Démo : 🟢 Active\n"
        f"📡 Pump.fun : 🟢 Scan actif",
        parse_mode="Markdown"
    )

async def add_dev_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage : `/trackdev ADRESSE NOM`", parse_mode="Markdown")
        return
    address = ctx.args[0].strip()
    label = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
    if storage.add_dev_wallet(address, label):
        await update.message.reply_text(
            f"✅ Dev *{label or address[:8]}* ajouté !\n"
            f"🔔 Alerte dès qu'il déploie un nouveau token.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ Ce dev est déjà tracké.")

async def list_dev_wallets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    devs = storage.get_dev_wallets()
    if not devs:
        await update.message.reply_text("_(Aucun dev tracké)_\n\nUtilise `/trackdev ADRESSE NOM`", parse_mode="Markdown")
        return
    msg = f"🛠️ *{len(devs)} Devs trackés :*\n━━━━━━━━━━━━━━━━━━━━\n"
    for w in devs[:50]:
        msg += f"• *{w.get('label','')}* `{w['address'][:8]}...`\n"
    if len(devs) > 50:
        msg += f"\n_... et {len(devs)-50} autres_"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def remove_dev_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage : `/untrackdev ADRESSE`", parse_mode="Markdown")
        return
    if storage.remove_dev_wallet(ctx.args[0].strip()):
        await update.message.reply_text("🗑️ Dev retiré.", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Dev introuvable.")

async def set_my_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        w = storage.get_user_wallet(chat_id)
        if w:
            await update.message.reply_text(f"👛 Wallet :\n`{w}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Aucun wallet.\nUsage : `/wallet ADRESSE`", parse_mode="Markdown")
        return
    storage.set_user_wallet(chat_id, ctx.args[0].strip())
    await update.message.reply_text(f"✅ Wallet connecté !\n`{ctx.args[0].strip()}`", parse_mode="Markdown")

async def my_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from config import Config
    config = Config()
    chat_id = str(update.effective_chat.id)
    wallet = storage.get_user_wallet(chat_id)
    if not wallet:
        await update.message.reply_text("❌ Connecte ton wallet : `/wallet ADRESSE`", parse_mode="Markdown")
        return
    await update.message.reply_text("⏳ Chargement...")
    sol = await get_sol_balance(wallet, config.HELIUS_RPC)
    await update.message.reply_text(
        f"👛 *Balance*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"◎ SOL : `{sol:.4f}`\n\n"
        f"🔗 [Solscan](https://solscan.io/account/{wallet})",
        parse_mode="Markdown", disable_web_page_preview=False
    )
