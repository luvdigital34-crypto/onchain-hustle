import logging
import httpx
import json
import base64

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TEXT_MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqClient:
    def __init__(self, api_key):
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def ask(self, prompt, system="", max_tokens=500):
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(GROQ_URL, headers=self.headers, json={"model": TEXT_MODEL, "max_tokens": max_tokens, "messages": messages})
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Groq error: {e}")
            return ""

    async def ask_with_image(self, prompt, image_bytes, max_tokens=600):
        """Envoie une image (bytes) + un prompt texte à un modèle vision."""
        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }]
            async with httpx.AsyncClient(timeout=40) as c:
                r = await c.post(GROQ_URL, headers=self.headers, json={
                    "model": VISION_MODEL, "max_tokens": max_tokens, "messages": messages
                })
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Groq vision error: {e}")
            return ""

    async def generate_token_idea(self, context, platform, author):
        return await self.ask(f"""Analyse ce contenu {platform} de {author} et génère une idée de meme coin Solana viral.

CONTENU: \"\"\"{context}\"\"\"

Réponds UNIQUEMENT avec ce format:
🪙 *Nom :* [nom fun]
📌 *Ticker :* $[3-5 lettres]
📝 *Description :* [1 phrase]
💬 *Slogan :* [slogan court]
🎨 *Logo :* [description visuelle]
📊 *Viral Score :* [⭐ à ⭐⭐⭐⭐⭐]
🔥 *Pourquoi ça va pumper :* [1 phrase]""", max_tokens=300)

    async def analyze_trend(self, content, source):
        result = await self.ask(f"""Analyse cette tendance depuis {source}: \"\"\"{content}\"\"\"

Réponds en JSON uniquement:
{{"score": 1-10, "type": "meme|narrative|trend|news", "summary": "résumé court", "token_opportunity": true/false, "urgency": "high|medium|low"}}""", max_tokens=200)
        try: return json.loads(result)
        except: return {"score": 5, "type": "trend", "summary": content[:100], "token_opportunity": False, "urgency": "low"}

    async def generate_token_from_image(self, description):
        return await self.ask(f"""Génère un meme coin Solana complet basé sur: {description}

Réponds UNIQUEMENT avec ce format:
🪙 *Nom :* [nom créatif]
📌 *Ticker :* $[3-5 lettres majuscules]
📝 *Description :* [2 phrases accrocheuses]
💬 *Slogan :* [slogan mémorable]
🎨 *Style du logo :* [description détaillée]
🌐 *Tags Pump.fun :* [tag1, tag2, tag3]
📊 *Potentiel :* [⭐ à ⭐⭐⭐⭐⭐]
💡 *Pourquoi ce coin va exploser :* [1 phrase]""", max_tokens=400)

    async def generate_token_from_real_image(self, image_bytes, caption=""):
        """Regarde vraiment l'image envoyée pour générer le token (pas juste la légende)."""
        extra = f"\nLégende fournie par l'utilisateur : {caption}" if caption else ""
        prompt = f"""Regarde cette image et génère un meme coin Solana complet basé sur ce que tu vois vraiment dessus (style, sujet, ambiance, couleurs).{extra}

Réponds UNIQUEMENT avec ce format:
🪙 *Nom :* [nom créatif basé sur l'image]
📌 *Ticker :* $[3-5 lettres majuscules]
📝 *Description :* [2 phrases accrocheuses basées sur ce que tu vois]
💬 *Slogan :* [slogan mémorable]
🎨 *Style du logo :* [description basée sur l'image réelle]
🌐 *Tags Pump.fun :* [tag1, tag2, tag3]
📊 *Potentiel :* [⭐ à ⭐⭐⭐⭐⭐]
💡 *Pourquoi ce coin va exploser :* [1 phrase]"""
        return await self.ask_with_image(prompt, image_bytes, max_tokens=400)

    async def analyze_profile_screenshot(self, image_bytes, user_note=""):
        """Analyse un screenshot de profil X/TikTok pour juger son authenticité/notoriété."""
        extra = f"\nNote de l'utilisateur : {user_note}" if user_note else ""
        prompt = f"""Regarde ce screenshot de profil de réseau social (X/Twitter ou TikTok).{extra}

Analyse et réponds en français avec :
1. Le pseudo/nom visible sur le profil
2. Le nombre d'abonnés visible (si affiché)
3. Est-ce que le compte semble authentique ou potentiellement fake (photo générique, bio vide, peu d'activité visible) ?
4. Reconnais-tu ce nom/pseudo comme une figure connue dans la crypto, les meme coins, ou ailleurs ? Sois honnête si tu ne le reconnais pas.
5. Une conclusion courte : ce compte semble-t-il fiable/influent ou non, sur la base de ce qui est visible ?

Sois concis et honnête, ne surestime pas ta confiance si tu ne reconnais pas la personne."""
        return await self.ask_with_image(prompt, image_bytes, max_tokens=500)
