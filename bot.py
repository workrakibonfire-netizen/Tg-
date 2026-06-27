import os
import random
import logging
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

# Import Python Telegram Bot v21+ modules
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# Load environment variables
load_dotenv()

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fetch Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
    TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))
except ValueError:
    logger.error("SUPER_ADMIN_ID and TARGET_CHAT_ID must be valid integers.")
    exit(1)

PORT = int(os.getenv("PORT", "10000"))

# Global App State Control
class AppState:
    def __init__(self):
        self.is_running = True
        self.interval = 30  # Default 30 seconds
        self.bg_task: asyncio.Task | None = None

state = AppState()

# Health Check Server for Render.com
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def log_message(self, format, *args):
        # Override to prevent excessive server log flooding
        return

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    logger.info(f"Health check server started on port {PORT}")
    server.serve_forever()

# Utility Data Generators
def generate_random_payment():
    methods = ["bKash", "Nagad", "Rocket", "Upay"]
    prefixes = ["017", "018", "013", "019", "016", "015", "014"]
    
    amount = random.randint(20, 500)
    method = random.choice(methods)
    
    prefix = random.choice(prefixes)
    suffix = f"{random.randint(0, 99):02d}"
    masked_number = f"{prefix}******{suffix}"
    
    # Bangladesh Timezone
    tz = ZoneInfo("Asia/Dhaka")
    now = datetime.now(tz)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%I:%M %p")
    
    # Markdown formatted text
    message = (
        "✅ *Withdrawal Successful*\n\n"
        "💳 *Payment Method:* {}\n"
        "📱 *Wallet Number:* {}\n"
        "💰 *Amount:* {} BDT\n"
        "📅 *Date:* {}\n"
        "🕒 *Time:* {}\n\n"
        "🎉 *Congratulations! Payment Sent Successfully.*"
    ).format(method, masked_number, amount, date_str, time_str)
    
    return message

# Background Task for Automatic Proof Delivery
async def proof_delivery_worker(application: Application):
    logger.info("Auto payment proof worker task started.")
    while True:
        try:
            if state.is_running:
                proof_text = generate_random_payment()
                try:
                    await application.bot.send_message(
                        chat_id=TARGET_CHAT_ID,
                        text=proof_text,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Payment proof successfully dispatched to chat ID: {TARGET_CHAT_ID}")
                except TelegramError as te:
                    logger.error(f"Telegram API Error during dispatch: {te}")
                except Exception as e:
                    logger.error(f"Unexpected transmission error: {e}")
            
            # Use dynamically adjustable sleep interval
            await asyncio.sleep(state.interval)
        except asyncio.CancelledError:
            logger.info("Auto payment proof worker task received cancel signal.")
            break
        except Exception as e:
            logger.error(f"Worker critical loop recovery caught: {e}")
            await asyncio.sleep(5) # Cooldown before re-attempting loop

# Admin Command Guard Filter
def is_admin(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == SUPER_ADMIN_ID

# Command Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("🚀 Bot initialized successfully and operational status monitoring is active.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    run_status = "Running" if state.is_running else "Stopped"
    status_msg = (
        f"📊 *System Operational Status*\n\n"
        f"▪️ *Engine Status:* {run_status}\n"
        f"▪️ *Current Interval:* {state.interval} seconds\n"
        f"▪️ *Target Destination:* `{TARGET_CHAT_ID}`"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")

async def on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if state.is_running:
        await update.message.reply_text("ℹ️ Auto proof delivery engine is already operational.")
    else:
        state.is_running = True
        logger.info("Bot execution resumed by Admin.")
        await update.message.reply_text("🟢 Auto proof delivery engine successfully started.")

async def off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not state.is_running:
        await update.message.reply_text("ℹ️ Auto proof delivery engine is already paused.")
    else:
        state.is_running = False
        logger.info("Bot execution paused by Admin.")
        await update.message.reply_text("🔴 Auto proof delivery engine paused.")

async def interval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("❌ Usage Syntax Error. Example: `/interval 30`", parse_mode="Markdown")
        return
    
    try:
        new_interval = int(context.args[0])
        if new_interval <= 0:
            raise ValueError()
        
        state.interval = new_interval
        logger.info(f"Execution dispatch interval adjusted to: {new_interval} seconds by Admin.")
        await update.message.reply_text(f"🎯 Broadcast interval updated successfully to *{new_interval} seconds*.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Validation Failed. Please provide a positive whole number.")

def main():
    # Enforce token check
    if not BOT_TOKEN:
        logger.error("CRITICAL: BOT_TOKEN environment variable missing. Application terminating.")
        return

    # Fire Web Service in Background Thread for Webhook Keep-Alive / Render metrics
    server_thread = threading.Thread(target=run_health_server, daemon=True)
    server_thread.start()

    # Build Application Instance
    application = Application.builder().token(BOT_TOKEN).build()

    # Link Admin Interaction Routes
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("on", on_cmd))
    application.add_handler(CommandHandler("off", off_cmd))
    application.add_handler(CommandHandler("interval", interval_cmd))

    # Access base event loop to register continuous worker task
    loop = asyncio.get_event_loop()
    state.bg_task = loop.create_task(proof_delivery_worker(application))

    # Initialize Bot Event Processing Engine via Long Polling
    logger.info("Starting production pipeline execution polling loop...")
    application.run_polling()

if __name__ == "__main__":
    main()
