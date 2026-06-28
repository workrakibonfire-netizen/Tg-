import os
import random
import logging
import asyncio
import threading
import string
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
        self.send_silent = True  
        
        # সামারি রিপোর্টের জন্য ট্র্যাকিং ভেরিয়েবলস
        self.total_sent_today = 0
        self.count_sent_today = 0
        
        # সফল মেসেজের কাউন্টার এবং পরবর্তী ফেইল্ড মেসেজের টার্গেট
        self.success_counter = 0
        self.next_failure_target = random.randint(10, 15) 

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

# র্যান্ডম TxID জেনারেটর
def generate_txid():
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(8))

# Utility Data Generators
def generate_proof_message():
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
    
    method_bn = "বিকাশ" if method == "bKash" else "নগদ"
    
    # ১০-১৫ টা সাকসেসের পর ১টা রিয়ালিস্টিক ফেইল্ড মেসেজ সিমুলেশন
    if state.success_counter >= state.next_failure_target:
        state.success_counter = 0
        state.next_failure_target = random.randint(10, 15)
        
        message = (
            "❌ *Withdrawal Failed / Rejected*\n\n"
            "💳 *Payment Method:* {}\n"
            "📱 *Wallet Number:* {}\n"
            "💰 *Amount:* {} BDT\n"
            "📅 *Date:* {}\n"
            "🕒 *Time:* {}\n\n"
            "⚠️ *Reason:* আপনার ওয়ালেট নম্বরে {} একাউন্ট করা নেই। দয়া করে সঠিক নম্বরটি চেক করে আবার চেষ্টা করুন।"
        ).format(method, masked_number, amount, date_str, time_str, method_bn)
        
        return message
    
    state.success_counter += 1
    state.total_sent_today += amount
    state.count_sent_today += 1
    txid = generate_txid()
    
    message = (
        "✅ *Withdrawal Successful*\n\n"
        "💳 *Payment Method:* {}\n"
        "📱 *Wallet Number:* {}\n"
        "💰 *Amount:* {} BDT\n"
        "🆔 *TxID:* {}\n"
        "📅 *Date:* {}\n"
        "🕒 *Time:* {}\n\n"
        "🎉 *Congratulations! Payment Sent Successfully.*"
    ).format(method, masked_number, amount, txid, date_str, time_str)
    
    return message

# Background Task for Automatic Proof Delivery
async def proof_delivery_worker(application: Application):
    while True:
        try:
            current_sleep_time = random.randint(state.min_interval, state.max_interval)
            await asyncio.sleep(current_sleep_time)
            
            if state.is_running:
                proof_text = generate_proof_message()
                try:
                    await application.bot.send_message(
                        chat_id=TARGET_CHAT_ID,
                        text=proof_text,
                        parse_mode="Markdown",
                        disable_notification=state.send_silent 
                    )
                except TelegramError:
                    pass
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)

# Daily Summary Worker (রাত ৮টায় বাংলাদেশ সময়)
async def daily_summary_worker(application: Application):
    tz = ZoneInfo("Asia/Dhaka")
    while True:
        try:
            now = datetime.now(tz)
            if now.hour == 20 and now.minute == 0:
                if state.count_sent_today > 0:
                    summary_msg = (
                        "📊 *⚡ DAILY PAYMENT SUMMARY REPORT ⚡*\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📅 *Date:* {now.strftime('%d/%m/%Y')}\n"
                        f"🚀 *Total Successful Payouts:* `{state.count_sent_today} Users`\n"
                        f"💰 *Total Amount Disbursed:* `{state.total_sent_today} BDT`\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "🤝 *Thank you for staying with us!*"
                    )
                    try:
                        await application.bot.send_message(
                            chat_id=TARGET_CHAT_ID,
                            text=summary_msg,
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
                    state.total_sent_today = 0
                    state.count_sent_today = 0
                await asyncio.sleep(60)
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)

# Admin Authorization Guard
def is_admin(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == SUPER_ADMIN_ID

# --- KEYBOARDS & MENUS ---

def get_admin_reply_keyboard():
    notif_button_text = "🔕 Notification: OFF (Silent)" if state.send_silent else "🔔 Notification: ON (Sound)"
    keyboard = [
        [KeyboardButton("🟢 Start Engine"), KeyboardButton("🔴 Stop Engine")],
        [KeyboardButton(notif_button_text)],
        [KeyboardButton("💰 Change Amount Limit"), KeyboardButton("⏱ Change Time/Interval")],
        [KeyboardButton("📊 View Live Status"), KeyboardButton("🧹 Clear Old Chat")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, selective=True)

def get_time_keyboard():
    keyboard = [
        [KeyboardButton("⏱ Random 20s - 1m"), KeyboardButton("⏱ Random 30s - 5m")],
        [KeyboardButton("⏱ Random 1m - 10m"), KeyboardButton("⏱ Random 5m - 30m")],
        [KeyboardButton("⏱ Random 10m - 1h"), KeyboardButton("⏱ Random 1h - 3h")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, selective=True)

def get_amount_keyboard():
    keyboard = [
        [KeyboardButton("💰 Range: 20 - 100 BDT"), KeyboardButton("💰 Range: 50 - 500 BDT")],
        [KeyboardButton("💰 Range: 100 - 1000 BDT"), KeyboardButton("💰 Range: 500 - 5000 BDT")],
        [KeyboardButton("💰 Range: 1000 - 10000 BDT"), KeyboardButton("💰 Range: 5000 - 25000 BDT")],
        [KeyboardButton("⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, selective=True)

def format_seconds(seconds):
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds < 3600:
        return f"{seconds // 60} minute(s)"
    return f"{seconds // 3600} hour(s)"

def get_status_text():
    run_status = "✨ Running / Active" if state.is_running else "💤 Stopped / Paused"
    notif_status = "🔕 OFF (Silent Mode)" if state.send_silent else "🔔 ON (Sound)"
    return (
        f"👑 *⚡ ADMIN CONTROL CENTER ⚡*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 *Bot Status:* {run_status}\n"
        f"📢 *User Notification:* `{notif_status}`\n"
        f"🎲 *Random Time Range:* `{format_seconds(state.min_interval)}` to `{format_seconds(state.max_interval)}`\n"
        f"💵 *Amount Matrix Range:* `{state.min_amount} - {state.max_amount} BDT`\n"
        f"📊 *Logged Today:* `{state.count_sent_today} items` | `{state.total_sent_today} BDT`\n"
        f"⏰ *Auto Summary Report:* `Everyday at 08:00 PM` (Dhaka Time)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

# Logic Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("👋 Welcome!", reply_markup=ReplyKeyboardRemove())
        return
    await update.message.reply_text(
        "👋 *Welcome, Admin!*\n\n🎛 সম্পূর্ণ এ-টু-জেড বাটন কন্ট্রোল প্যানেল রেডি করা হয়েছে। নিচে ক্লিক করে যেকোনো সাব-মেনুতে প্রবেশ করতে পারেন।",
        reply_markup=get_admin_reply_keyboard(),
        parse_mode="Markdown"
    )

async def admin_button_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    text = update.message.text

    if text == "🟢 Start Engine":
        state.is_running = True
        await update.message.reply_text("🟢 *Engine Started:* পেমেন্ট প্রুফ জেনারেশন চালু হয়েছে।")
    elif text == "🔴 Stop Engine":
        state.is_running = False
        await update.message.reply_text("🔴 *Engine Stopped:* পেমেন্ট প্রুফ জেনারেশন বন্ধ করা হয়েছে।")
    elif text == "📊 View Live Status":
        await update.message.reply_text(get_status_text(), parse_mode="Markdown")
    elif text == "🧹 Clear Old Chat":
        status_msg = await update.message.reply_text("⏳ *Processing:* চ্যাট পরিষ্কার করা হচ্ছে...")
        current_msg_id = status_msg.message_id
        deleted_count = 0
        for i in range(1, 101):
            try:
                await context.bot.delete_message(chat_id=TARGET_CHAT_ID, message_id=current_msg_id - i)
                deleted_count += 1
                await asyncio.sleep(0.05)
            except TelegramError:
                continue
        await status_msg.edit_text(f"✨ *Clean Complete:* `{deleted_count}` টি মেসেজ ডিলিট করা হয়েছে।")
    elif text == "⏱ Change Time/Interval":
        await update.message.reply_text("⏱ *পোস্ট করার র্যান্ডম সময় রেঞ্জ সিলেক্ট করুন:*", reply_markup=get_time_keyboard(), parse_mode="Markdown")
    elif text == "💰 Change Amount Limit":
        await update.message.reply_text("💰 *টাকার রেঞ্জ লিমিট সিলেক্ট করুন:*", reply_markup=get_amount_keyboard(), parse_mode="Markdown")
    elif text == "⬅️ Back to Main Menu":
        await update.message.reply_text("🎛 মূল মেনুতে ফিরে আসা হয়েছে।", reply_markup=get_admin_reply_keyboard())
    elif "Notification: OFF" in text:
        state.send_silent = False
        await update.message.reply_text("🔔 *Notification Enabled:* সাউন্ড মোড অন করা হয়েছে।", reply_markup=get_admin_reply_keyboard(), parse_mode="Markdown")
    elif "Notification: ON" in text:
        state.send_silent = True
        await update.message.reply_text("🔕 *Notification Disabled:* সাইলেন্ট মোড অন করা হয়েছে।", reply_markup=get_admin_reply_keyboard(), parse_mode="Markdown")
    
    # --- Time Sub Menu Options ---
    elif text == "⏱ Random 20s - 1m":
        state.min_interval, state.max_interval = 20, 60
        await update.message.reply_text("🎯 *Adjusted:* ২০ সেকেন্ড থেকে ১ মিনিট র্যান্ডম টাইম সেট হয়েছে।")
    elif text == "⏱ Random 30s - 5m":
        state.min_interval, state.max_interval = 30, 300
        await update.message.reply_text("🎯 *Adjusted:* ৩০ সেকেন্ড থেকে ৫ মিনিট র্যান্ডম টাইম সেট হয়েছে।")
    elif text == "⏱ Random 1m - 10m":
        state.min_interval, state.max_interval = 60, 600
        await update.message.reply_text("🎯 *Adjusted:* ১ মিনিট থেকে ১০ মিনিট র্যান্ডম টাইম সেট হয়েছে।")
    elif text == "⏱ Random 5m - 30m":
        state.min_interval, state.max_interval = 300, 1800
        await update.message.reply_text("🎯 *Adjusted:* ৫ মিনিট থেকে ৩০ মিনিট র্যান্ডম টাইম সেট হয়েছে।")
    elif text == "⏱ Random 10m - 1h":
        state.min_interval, state.max_interval = 600, 3600
        await update.message.reply_text("🎯 *Adjusted:* ১০ মিনিট থেকে ১ ঘণ্টা র্যান্ডম টাইম সেট হয়েছে।")
    elif text == "⏱ Random 1h - 3h":
        state.min_interval, state.max_interval = 3600, 10800
        await update.message.reply_text("🎯 *Adjusted:* ১ ঘণ্টা থেকে ৩ ঘণ্টা র্যান্ডম টাইম সেট হয়েছে।")
    
    # --- Amount Sub Menu Options ---
    elif text == "💰 Range: 20 - 100 BDT":
        state.min_amount, state.max_amount = 20, 100
        await update.message.reply_text("🎯 *Adjusted:* টাকার লিমিট ২০ থেকে ১০০ BDT সেট হয়েছে।")
    elif text == "💰 Range: 50 - 500 BDT":
        state.min_amount, state.max_amount = 50, 500
        await update.message.reply_text("🎯 *Adjusted:* টাকার লিমিট ৫০ থেকে ৫০০ BDT সেট হয়েছে।")
    elif text == "💰 Range: 100 - 1000 BDT":
        state.min_amount, state.max_amount = 100, 1000
        await update.message.reply_text("🎯 *Adjusted:* ১০০ থেকে ১০০০ BDT সেট হয়েছে।")
    elif text == "💰 Range: 500 - 5000 BDT":
        state.min_amount, state.max_amount = 500, 5000
        await update.message.reply_text("🎯 *Adjusted:* ৫০০ থেকে ৫০০০ BDT সেট হয়েছে।")
    elif text == "💰 Range: 1000 - 10000 BDT":
        state.min_amount, state.max_amount = 1000, 10000
        await update.message.reply_text("🎯 *Adjusted:* ১০০০ থেকে ১০,০০০ BDT সেট হয়েছে।")
    elif text == "💰 Range: 5000 - 25000 BDT":
        state.min_amount, state.max_amount = 5000, 25000
        await update.message.reply_text("🎯 *Adjusted:* ৫০০০ থেকে ২৫,০০০ BDT সেট হয়েছে।")

async def post_init(application: Application) -> None:
    asyncio.create_task(proof_delivery_worker(application))
    asyncio.create_task(daily_summary_worker(application))
    logger.info("Pipelines launched.")

def main():
    if not BOT_TOKEN:
        return
    server_thread = threading.Thread(target=run_health_server, daemon=True)
    server_thread.start()

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("admin", start_cmd)) 
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_text_handler))
    
    application.run_polling()

if __name__ == "__main__":
    main()
