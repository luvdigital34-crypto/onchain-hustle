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
            txns_h1 = pair.get("txns", {}).get("h1", {})
            return {
                "name":       pair.get("baseToken",{}).get("name","Unknown"),
                "symbol":     pair.get("baseToken",{}).get("symbol",""),
                "price_usd":  float(pair.get("priceUsd", 0) or 0),
                "market_cap": float(pair.get("marketCap", 0) or 0),
                "volume_24h": float(pair.get("volume",{}).get("h24", 0) or 0),
                "change_24h": float(pair.get("priceChange",{}).get("h24", 0) or 0),
                "liquidity":  float(pair.get("liquidity",{}).get("usd", 0) or 0),
                "dex_url":    pair.get("url",""),
                "buys_h1":    int(txns_h1.get("buys", 0) or 0),
                "sells_h1":   int(txns_h1.get("sells", 0) or 0),
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

async def get_top_holder_pct(mint, helius_rpc):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(helius_rpc, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint]
            })
            data = r.json().get("result", {}).get("value", [])
            if not data:
                return 0.0

            supply_r = await c.post(helius_rpc, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenSupply",
                "params": [mint]
            })
            supply = float(supply_r.json().get("result", {}).get("value", {}).get("uiAmount", 0) or 0)
            if supply <= 0:
                return 0.0

            top_amount = float(data[0].get("uiAmount", 0) or 0)
            return round((top_amount / supply) * 100, 1)
    except Exception as e:
        logger.error(f"get_top_holder_pct error: {e}")
        return 0.0

async def get_new_mint_from_signature(signature, helius_rpc):
    """Récupère le mint d'un nouveau token à partir d'une signature de transaction (pour le listener temps réel)."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(helius_rpc, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            })
            result = r.json().get("result")
            if not result:
                return None
            meta = result.get("meta", {})
            post_balances = meta.get("postTokenBalances", [])
            pre_balances = meta.get("preTokenBalances", [])
            pre_mints = {b.get("mint") for b in pre_balances}
            for b in post_balances:
                mint = b.get("mint")
                if mint and mint not in pre_mints and mint.endswith("pump"):
                    return mint
            return None
    except Exception as e:
        logger.error(f"get_new_mint_from_signature error: {e}")
        return None
