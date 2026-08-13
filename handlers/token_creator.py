import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ai.groq_client import GroqClient
from config import Config

logger = logging.getLogger(__name__)
config = Config()
groq = GroqClient(config.GROQ_API_KEY)
waiting_for_image = set()

async def create_token_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    waiting_for_image.add(update.effective_chat.id)
    await update.message.reply_text(
        "🪙 *Créer un Meme Coin*\n\n"
        "📸 Envoie une image et je génère :\n"
        "• Nom + Ticker\n• Description + Slogan\n"
        "• Style logo\n• Tags Pump.fun\n• Lien pour déployer\n\n"
        "_Envoie ton image !_",
        parse_mode="Markdown"
    )

async def handle_token_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in waiting_for_image:
        return
    waiting_for_image.discard(chat_id)
    await update.message.reply_text("⏳ Génération en cours...")
    caption = update.message.caption or "Image sans description"
    result = await groq.generate_token_from_image(caption)
    if not result:
        await update.message.reply_text("❌ Erreur. Réessaie avec `/create`", parse_mode="Markdown")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Déployer sur Pump.fun", url="https://pump.fun/create")],
        [InlineKeyboardButton("🎨 Logo (Canva)", url="https://www.canva.com"),
         InlineKeyboardButton("🌐 Site (Carrd)", url="https://carrd.co")],
    ])
    await update.message.reply_text(
        f"🪙 *Ton Meme Coin est prêt !*\n━━━━━━━━━━━━━━━━━━━━\n{result}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Pour lancer :*\n"
        f"1️⃣ Clique Pump.fun\n2️⃣ Connecte Phantom\n"
        f"3️⃣ Remplis les infos\n4️⃣ Lance pour ~0.02 SOL ✅",
        parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True
    )
