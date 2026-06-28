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
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
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
        self.min_amount = 20  
        self.max_amount = 500  
        self.min_interval = 20   
        self.max_interval = 300  
        self.send_silent = True  # True হলে সাইলেন্ট (নোটিফিকেশন যাবে না), False হলে সাউন্ড যাবে

state = AppState()

# Health Check Server for Render.com
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def log_message(self, format, *args):
        return

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    logger.info(f"Health check server started on port {PORT}")
    server.serve_forever()

# Utility Data Generators
def generate_random_payment():
    methods = ["bKash", "Nagad"]
    prefixes = ["017", "018", "013", "019", "016", "015", "014"]
    
    amount = random.randint(state.min_amount, state.max_amount)
    method = random.choice(methods)
    
    prefix = random.choice(prefixes)
    suffix = f"{random.randint(0, 99):02d}"
    masked_number = f"{prefix}\*\*\*\*\*\*{suffix}"
    
    tz = ZoneInfo("Asia/Dhaka")
    now = datetime.now(tz)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%I:%M %p")
    
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

# Background Task for Automatic Proof Delivery with Random Interval
async def proof_delivery_worker(application: Application):
    logger.info("Auto payment proof worker task started.")
    while True:
        try:
            current_sleep_time = random.randint(state.min_interval, state.max_interval)
            logger.info(f"Next proof will be sent after a random interval of {current_sleep_time} seconds.")
            
            await asyncio.sleep(current_sleep_time)
            
            if state.is_running:
                proof_text = generate_random_payment()
                try:
                    # state.send_silent এর উপর ভিত্তি করে নোটিফিকেশন অন/অফ হবে
                    await application.bot.send_message(
                        chat_id=TARGET_CHAT_ID,
                        text=proof_text,
                        parse_mode="Markdown",
                        disable_notification=state.send_silent 
                    )
                    logger.info(f"Payment proof dispatched. Silent Mode: {state.send_silent}")
                except TelegramError as te:
                    logger.error(f"Telegram API Error during dispatch: {te}")
                except Exception as e:
                    logger.error(f"Unexpected transmission error: {e}")
            
        except asyncio.CancelledError:
            logger.info("Auto payment proof worker task received cancel signal.")
            break
        except Exception as e:
            logger.error(f"Worker critical loop recovery caught: {e}")
            await asyncio.sleep(5)

# Admin Command Guard Filter
def is_admin(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == SUPER_ADMIN_ID

# Main Admin Keyboard (ডায়নামিক বাটন সহ)
def get_admin_reply_keyboard():
    # নোটিফিকেশন স্ট্যাটাস অনুযায়ী বাটনের টেক্সট সেট হবে
    notif_button_text = "🔕 Notification: OFF (Silent)" if state.send_silent else "🔔 Notification: ON (Sound)"
    
    keyboard = [
        [KeyboardButton("🟢 Start Engine"), KeyboardButton("🔴 Stop Engine")],
        [KeyboardButton(notif_button_text)],
        [KeyboardButton("⏱ Preset Quick Time"), KeyboardButton("📊 View Live Status")],
        [KeyboardButton("🧹 Clear Old Chat")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, selective=True)

# Time Selection Sub-Keyboard
def get_time_keyboard():
    keyboard = [
        [KeyboardButton("⏱ Random 20s - 1m"), KeyboardButton("⏱ Random 30s - 5m")],
        [KeyboardButton("⏱ Random 1m - 10m"), KeyboardButton("⏱ Random 5m - 30m")],
        [KeyboardButton("⬅️ Back to Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, selective=True)

# Seconds to Format Conversion Helper
def format_seconds(seconds):
    if seconds < 60:
        return f"{seconds} seconds"
    return f"{seconds // 60} minute(s)"

def get_status_text():
    run_status = "✨ Running / Active" if state.is_running else "💤 Stopped / Paused"
    notif_status = "🔕 OFF (Silent Mode)" if state.send_silent else "🔔 ON (Sound Notification)"
    
    return (
        f"👑 *⚡ ADMIN CONTROL CENTER ⚡*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 *Bot Current Status:* {run_status}\n"
        f"📢 *User Notification:* `{notif_status}`\n"
        f"🎲 *Random Time Range:* `{format_seconds(state.min_interval)}` to `{format_seconds(state.max_interval)}`\n"
        f"💵 *Amount Matrix Range:* `{state.min_amount} - {state.max_amount} BDT`\n"
        f"📢 *Destination Chat ID:* `{TARGET_CHAT_ID}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Quick Settings via Text Commands:*\n"
        f"▫️ `/timerange 20 300` (Set Custom Time Range in Seconds)\n"
        f"▫️ `/range 50 200` (Set Custom BDT limits)"
    )

# Command Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("👋 Welcome! I am an automated payment proof bot.", reply_markup=ReplyKeyboardRemove())
        return
        
    await update.message.reply_text(
        "👋 *Welcome Back, Admin!*\n\n"
        "🎛 Your control panel has been loaded below. Use buttons or text commands to manage settings.",
        reply_markup=get_admin_reply_keyboard(),
        parse_mode="Markdown"
    )

async def range_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ *Usage Example:* `/range 20 100`", parse_mode="Markdown")
        return
    try:
        min_val = int(context.args[0])
        max_val = int(context.args[1])
        if min_val <= 0 or max_val <= 0 or min_val > max_val:
            raise ValueError()
        state.min_amount = min_val
        state.max_amount = max_val
        await update.message.reply_text(f"🎯 *Success:* Amount limits adjusted to *{min_val} - {max_val} BDT*.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ *Error:* Please enter valid whole numbers.")

async def timerange_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ *Usage Example (in seconds):* `/timerange 20 300` (For 20s to 5m)", parse_mode="Markdown")
        return
    try:
        min_t = int(context.args[0])
        max_t = int(context.args[1])
        if min_t <= 0 or max_t <= 0 or min_t > max_t:
            raise ValueError()
        state.min_interval = min_t
        state.max_interval = max_t
        await update.message.reply_text(f"🎯 *Success:* Random post time range set to *{format_seconds(min_t)} - {format_seconds(max_t)}*.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ *Error:* Please enter valid numbers in seconds.")

# Handler for Admin Panel Buttons text input
async def admin_button_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    text = update.message.text

    if text == "🟢 Start Engine":
        if state.is_running:
            await update.message.reply_text("ℹ️ *System Message:* The engine is already active.")
        else:
            state.is_running = True
            await update.message.reply_text("🟢 *Engine Started:* Auto random payment proof generation is live.")
            
    elif text == "🔴 Stop Engine":
        if not state.is_running:
            await update.message.reply_text("ℹ️ *System Message:* The engine is already stopped.")
        else:
            state.is_running = False
            await update.message.reply_text("🔴 *Engine Stopped:* Auto production has been paused.")
            
    elif text == "📊 View Live Status":
        await update.message.reply_text(get_status_text(), parse_mode="Markdown")
        
    elif text == "🧹 Clear Old Chat":
        status_msg = await update.message.reply_text("⏳ *Processing:* Removing the last 100 messages...")
        current_msg_id = status_msg.message_id
        deleted_count = 0
        for i in range(1, 101):
            target_msg_id = current_msg_id - i
            try:
                await context.bot.delete_message(chat_id=TARGET_CHAT_ID, message_id=target_msg_id)
                deleted_count += 1
                await asyncio.sleep(0.05)
            except TelegramError:
                continue
        await status_msg.edit_text(f"✨ *Clean Complete:* Deleted `{deleted_count}` messages successfully.")

    elif text == "⏱ Preset Quick Time":
        await update.message.reply_text(
            "⏱ *Select a Ready Random Time Range:*",
            reply_markup=get_time_keyboard(),
            parse_mode="Markdown"
        )

    elif text == "⬅️ Back to Menu":
        await update.message.reply_text(
            "🎛 Returning to Main Admin Menu.",
            reply_markup=get_admin_reply_keyboard()
        )

    # ওয়ান-ক্লিক নোটিফিকেশন অন/অফ লজিক (টগল বাটন)
    elif "Notification: OFF" in text:
        state.send_silent = False # সাইলেন্ট মুড অফ অর্থাৎ নোটিফিকেশন সাউন্ড অন হবে
        await update.message.reply_text(
            "🔔 *Notification Enabled:* এখন থেকে চ্যানেলে মেসেজ গেলে মেম্বাররা নোটিফিকেশন সাউন্ড পাবে।",
            reply_markup=get_admin_reply_keyboard(),
            parse_mode="Markdown"
        )
        
    elif "Notification: ON" in text:
        state.send_silent = True # সাইলেন্ট মুড অন অর্থাৎ নোটিফিকেশন সাউন্ড অফ হবে
        await update.message.reply_text(
            "🔕 *Notification Disabled:* এখন থেকে মেসেজগুলো একদম সাইলেন্টলি চ্যানেলে পোস্ট হবে (কোনো সাউন্ড হবে না)।",
            reply_markup=get_admin_reply_keyboard(),
            parse_mode="Markdown"
        )

    # Preset Time Selection Buttons Logic
    elif text == "⏱ Random 20s - 1m":
        state.min_interval = 20
        state.max_interval = 60
        await update.message.reply_text("🎯 *Time Range Adjusted:* Randomly between 20 seconds and 1 minute.")
    elif text == "⏱ Random 30s - 5m":
        state.min_interval = 30
        state.max_interval = 300
        await update.message.reply_text("🎯 *Time Range Adjusted:* Randomly between 30 seconds and 5 minutes.")
    elif text == "⏱ Random 1m - 10m":
        state.min_interval = 60
        state.max_interval = 600
        await update.message.reply_text("🎯 *Time Range Adjusted:* Randomly between 1 minute and 10 minutes.")
    elif text == "⏱ Random 5m - 30m":
        state.min_interval = 300
        state.max_interval = 1800
        await update.message.reply_text("🎯 *Time Range Adjusted:* Randomly between 5 minutes and 30 minutes.")

async def post_init(application: Application) -> None:
    asyncio.create_task(proof_delivery_worker(application))
    logger.info("Background tasks attached via post_init hook.")

def main():
    if not BOT_TOKEN:
        logger.error("CRITICAL: BOT_TOKEN missing.")
        return

    server_thread = threading.Thread(target=run_health_server, daemon=True)
    server_thread.start()

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Commands
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("admin", start_cmd)) 
    application.add_handler(CommandHandler("range", range_cmd))
    application.add_handler(CommandHandler("timerange", timerange_cmd))
    
    # Text Message Handler for Keyboard Buttons
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_text_handler))

    logger.info("Starting polling loop...")
    application.run_polling()

if __name__ == "__main__":
    main()