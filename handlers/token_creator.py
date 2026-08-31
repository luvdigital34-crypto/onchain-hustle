import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ai.groq_client import GroqClient
from config import Config

logger = logging.getLogger(__name__)
config = Config()
groq = GroqClient(config.GROQ_API_KEY)

waiting_for_image = set()
waiting_for_whois = set()


async def create_token_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    waiting_for_image.add(update.effective_chat.id)
    waiting_for_whois.discard(update.effective_chat.id)
    await update.message.reply_text(
        "🪙 *Créer un Meme Coin*\n\n"
        "📸 Envoie une image et l'IA va vraiment regarder ce qu'il y a dessus pour générer :\n"
        "• Nom + Ticker\n• Description + Slogan\n"
        "• Style logo\n• Tags Pump.fun\n• Lien pour déployer\n\n"
        "_Envoie ton image !_",
        parse_mode="Markdown"
    )


async def whois_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    waiting_for_whois.add(update.effective_chat.id)
    waiting_for_image.discard(update.effective_chat.id)
    await update.message.reply_text(
        "🔎 *Analyse de profil (X / TikTok)*\n\n"
        "📸 Envoie un screenshot du profil du créateur.\n"
        "Tu peux ajouter une note en légende (ex: \"il suit tel et tel compte\") pour aider l'analyse.\n\n"
        "⚠️ _L'IA ne peut analyser que ce qui est visible sur l'image, elle ne se connecte pas à X/TikTok en direct._",
        parse_mode="Markdown"
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Dispatcher unique pour toutes les photos reçues — route vers /create ou /whois selon le contexte."""
    chat_id = update.effective_chat.id

    if chat_id in waiting_for_image:
        waiting_for_image.discard(chat_id)
        await _handle_create_token(update, ctx)
    elif chat_id in waiting_for_whois:
        waiting_for_whois.discard(chat_id)
        await _handle_whois(update, ctx)
    # sinon : photo envoyée sans commande active, on ignore silencieusement


async def _download_photo_bytes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    byte_data = await file.download_as_bytearray()
    return bytes(byte_data)


async def _handle_create_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Analyse de l'image en cours...")
    try:
        image_bytes = await _download_photo_bytes(update, ctx)
    except Exception as e:
        logger.error(f"Erreur téléchargement image /create: {e}")
        await update.message.reply_text("❌ Erreur lors du téléchargement de l'image. Réessaie avec `/create`", parse_mode="Markdown")
        return

    caption = update.message.caption or ""
    result = await groq.generate_token_from_real_image(image_bytes, caption)
    if not result:
        await update.message.reply_text("❌ Erreur d'analyse. Réessaie avec `/create`", parse_mode="Markdown")
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


async def _handle_whois(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Analyse du profil en cours...")
    try:
        image_bytes = await _download_photo_bytes(update, ctx)
    except Exception as e:
        logger.error(f"Erreur téléchargement image /whois: {e}")
        await update.message.reply_text("❌ Erreur lors du téléchargement de l'image. Réessaie avec `/whois`", parse_mode="Markdown")
        return

    user_note = update.message.caption or ""
    result = await groq.analyze_profile_screenshot(image_bytes, user_note)
    if not result:
        await update.message.reply_text("❌ Erreur d'analyse. Réessaie avec `/whois`", parse_mode="Markdown")
        return

    await update.message.reply_text(
        f"🔎 *Analyse du profil*\n━━━━━━━━━━━━━━━━━━━━\n{result}\n\n"
        f"_Analyse basée uniquement sur ce qui est visible sur le screenshot._",
        parse_mode="Markdown"
    )
