import logging
import httpx

logger = logging.getLogger(__name__)
SOL_MINT = "So11111111111111111111111111111111111111112"

async def get_sol_balance(address, helius_rpc):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(helius_rpc, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[address]})
            return r.json().get("result",{}).get("value",0) / 1e9
    except: return 0.0

async def get_token_info(mint):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
            pairs = r.json().get("pairs", [])
            if not pairs: return {}
            pair = sorted(pairs, key=lambda x: float(x.get("liquidity",{}).get("usd",0) or 0), reverse=True)[0]
            return {
                "name":       pair.get("baseToken",{}).get("name","Unknown"),
                "symbol":     pair.get("baseToken",{}).get("symbol",""),
                "price_usd":  float(pair.get("priceUsd", 0) or 0),
                "market_cap": float(pair.get("marketCap", 0) or 0),
                "volume_24h": float(pair.get("volume",{}).get("h24", 0) or 0),
                "change_24h": float(pair.get("priceChange",{}).get("h24", 0) or 0),
                "liquidity":  float(pair.get("liquidity",{}).get("usd", 0) or 0),
                "dex_url":    pair.get("url",""),
            }
    except Exception as e:
        logger.error(f"Token info error: {e}")
        return {}

async def get_jupiter_quote(input_mint, output_mint, amount_lamports):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://quote-api.jup.ag/v6/quote", params={
                "inputMint": input_mint, "outputMint": output_mint,
                "amount": amount_lamports, "slippageBps": 100,
            })
            return r.json()
    except: return {}

async def get_wallet_txs(address, helius_rpc, limit=10):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(helius_rpc, json={"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress","params":[address,{"limit":limit}]})
            return r.json().get("result", [])
    except: return []

async def get_new_tokens_pump(limit=20):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.dexscreener.com/token-profiles/latest/v1")
            tokens = r.json() if isinstance(r.json(), list) else []
            return [t for t in tokens if t.get("chainId") == "solana"][:limit]
    except Exception as e:
        logger.error(f"New tokens error: {e}")
        return []
