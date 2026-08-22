import asyncio
import logging
import threading
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from handlers.commands import (
    start, help_cmd, status_cmd,
    add_dev_wallet, list_dev_wallets, remove_dev_wallet,
    set_my_wallet, my_balance
)
from handlers.trading import buy_cmd, sell_cmd, trade_buttons
from handlers.token_creator import create_token_cmd, handle_token_image
from handlers.demo_trading import demo_start_cmd, demo_status_cmd, demo_stop_cmd
from scrapers.dev_tracker import DevTracker
from scrapers.trend_hunter import TrendHunter
from scrapers.position_monitor import PositionMonitor
from utils.storage import Storage
from config import Config

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OnChainHunter is running")
    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"🌐 Health server on port {port}")
    server.serve_forever()


async def run_bot():
    config = Config()
    config.validate()
    storage = Storage(config.DATA_FILE)

    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("help",          help_cmd))
    app.add_handler(CommandHandler("status",        status_cmd))
    app.add_handler(CommandHandler("trackdev",      add_dev_wallet))
    app.add_handler(CommandHandler("devs",          list_dev_wallets))
    app.add_handler(CommandHandler("untrackdev",    remove_dev_wallet))
    app.add_handler(CommandHandler("wallet",        set_my_wallet))
    app.add_handler(CommandHandler("balance",       my_balance))
    app.add_handler(CommandHandler("buy",           buy_cmd))
    app.add_handler(CommandHandler("sell",          sell_cmd))
    app.add_handler(CommandHandler("create",        create_token_cmd))
    app.add_handler(CommandHandler("demo",          demo_start_cmd))
    app.add_handler(CommandHandler("demo_status",   demo_status_cmd))
    app.add_handler(CommandHandler("demo_stop",     demo_stop_cmd))
    app.add_handler(CallbackQueryHandler(trade_buttons))
    app.add_handler(MessageHandler(filters.PHOTO, handle_token_image))

    devs     = DevTracker(config, storage, app.bot)
    trends   = TrendHunter(config, storage, app.bot)
    monitor  = PositionMonitor(config, storage, app.bot)

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("🔫 OnChainHunter démarré !")
        await asyncio.gather(devs.run(), trends.run(), monitor.run())


if __name__ == "__main__":
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    asyncio.run(run_bot())
