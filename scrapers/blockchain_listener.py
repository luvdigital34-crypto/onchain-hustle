import asyncio
import json
import logging
import websockets
from utils.solana import get_new_mint_from_signature
from config import Config

logger = logging.getLogger(__name__)

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class BlockchainListener:
    """
    Écoute en direct la blockchain Solana via websocket Helius pour détecter
    les nouveaux tokens pump.fun à la seconde près (au lieu d'attendre le polling Dexscreener).
    Note : c'est du best-effort — si la connexion tombe, elle se reconnecte automatiquement.
    Le polling Dexscreener (dev_tracker) reste actif en parallèle comme filet de sécurité.
    """

    def __init__(self, config: Config, on_new_mint):
        self.config = config
        self.on_new_mint = on_new_mint
        self.retry_delay = 2

    async def run(self):
        logger.info("⚡ Blockchain listener démarré (websocket Helius temps réel)")
        while True:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"Blockchain listener error: {e}, reconnexion dans {self.retry_delay}s")
            await asyncio.sleep(self.retry_delay)
            self.retry_delay = min(self.retry_delay * 2, 60)

    async def _connect_and_listen(self):
        async with websockets.connect(self.config.HELIUS_WSS, ping_interval=20, ping_timeout=20) as ws:
            self.retry_delay = 2
            subscribe_msg = {
                "jsonrpc": "2.0", "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [PUMP_PROGRAM_ID]},
                    {"commitment": "confirmed"}
                ]
            }
            await ws.send(json.dumps(subscribe_msg))
            logger.info("⚡ Abonné aux logs pump.fun en temps réel")

            async for message in ws:
                try:
                    data = json.loads(message)
                    result = data.get("params", {}).get("result", {})
                    value = result.get("value", {})
                    logs = value.get("logs", [])
                    signature = value.get("signature")

                    if not signature or value.get("err"):
                        continue

                    is_create = any("Instruction: Create" in log for log in logs)
                    if not is_create:
                        continue

                    mint = await get_new_mint_from_signature(signature, self.config.HELIUS_RPC)
                    if mint:
                        logger.info(f"⚡ Nouveau token détecté en temps réel : {mint}")
                        await self.on_new_mint(mint)
                except Exception as e:
                    logger.error(f"Erreur traitement message websocket: {e}")
