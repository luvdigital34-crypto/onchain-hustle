import logging
import httpx
import json

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

class GroqClient:
    def __init__(self, api_key):
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def ask(self, prompt, system="", max_tokens=500):
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(GROQ_URL, headers=self.headers, json={"model": "llama3-8b-8192", "max_tokens": max_tokens, "messages": messages})
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Groq error: {e}")
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
