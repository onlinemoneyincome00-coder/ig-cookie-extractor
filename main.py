import os
import logging
import json
import time
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from instagrapi import Client
import pyotp

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

GET_USERNAMES, GET_PASSWORD, GET_2FA = range(3)
user_data_store = {}

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "বট চালু করুন"),
        BotCommand("restart", "বট রিস্টার্ট করুন")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
        
    keyboard = [[KeyboardButton("🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🤖 *ইনস্টাগ্রাম কুকি এক্সট্রাক্টর বটে স্বাগতম!*\n\n"
        "কাজ শুরু করতে নিচের বাটনে চাপ দিন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
        
    keyboard = [[KeyboardButton("🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🔄 *বট রিস্টার্ট করা হয়েছে!*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def start_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 ইউজারনেমগুলো দিন (প্রতি লাইনে একটি করে):", parse_mode="Markdown")
    return GET_USERNAMES

async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    usernames = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not usernames:
        await update.message.reply_text("⚠️ অন্তত একটি ইউজারনেম দিন।")
        return GET_USERNAMES

    user_data_store[update.effective_user.id] = {"usernames": usernames}
    await update.message.reply_text("🔑 পাসওয়ার্ড দিন:")
    return GET_PASSWORD

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশনের মেয়াদ শেষ। /restart দিন।")
        return ConversationHandler.END
        
    user_data_store[user_id]["password"] = password
    usernames = user_data_store[user_id]["usernames"]
    
    await update.message.reply_text(f"🔐 ঠিক একই সিরিয়ালে {len(usernames)} টি 2FA কি (Key) দিন:")
    return GET_2FA

async def receive_2fa_and_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    keys = [line.strip() for line in text.split('\n') if line.strip()]
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশনের মেয়াদ শেষ। /restart দিন।")
        return ConversationHandler.END
        
    data = user_data_store[user_id]
    usernames = data["usernames"]
    password = data["password"]
    
    if len(keys) != len(usernames):
        await update.message.reply_text(f"⚠️ ইউজারনেম ({len(usernames)}) এবং কি ({len(keys)}) এর সংখ্যা মিল থাকতে হবে।")
        return GET_2FA

    await update.message.reply_text("🔄 সেশন এবং কুকিজ এক্সট্রাক্ট করা হচ্ছে...")

    for i, username in enumerate(usernames):
        tfa_key = keys[i]
        cl = Client()
        
        # সেশন ফাইল হ্যান্ডলিং (আগে থেকে কোনো সেশন থাকলে তা লোড করার চেষ্টা করবে)
        session_file = f"session_{username}.json"
        if os.path.exists(session_file):
            try:
                cl.load_settings(session_file)
            except Exception:
                pass

        cl.set_user_agent("Instagram 300.0.0.25.112 Android (31/12; 480dpi; 1080x2340; Samsung; Galaxy S21; SM-G991B; exynos2100; en_US; 452345121)")
        cl.delay_range = [3, 7]
        
        try:
            # যদি অলরেডি লগইন করা থাকে তবে নতুন করে পাসওয়ার্ড লাগবে না
            if not cl.get_settings():
                totp_code = pyotp.TOTP(tfa_key.replace(" ", "")).now()
                cl.login(username, password, verification_code=totp_code)
                cl.dump_settings(session_file) # সফল হলে সেশন সেভ করে রাখা
            
            cookies = cl.get_settings()
            
            filename = f"cookie_{username}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(json.dumps(cookies, indent=4))
            
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ *সিরিয়াল {i+1}: সফল!*\n👤 অ্যাকাউন্ট: `{username}`"
                )
            if os.path.exists(filename):
                os.remove(filename)

        except Exception as e:
            err_str = str(e).lower()
            if "challenge_required" in err_str:
                reason = "অ্যাকাউন্ট সিকিউরিটি চেকপয়েন্টে (Challenge) গেছে। একবার ব্রাউজারে লগইন করে ভেরিফাই করুন।"
            elif "bad password" in err_str:
                reason = "পাসওয়ার্ড ভুল।"
            elif "two_factor" in err_str:
                reason = "2FA কি সঠিক নয়।"
            else:
                reason = f"টেকনিক্যাল সমস্যা: {str(e)}"

            await update.message.reply_text(
                f"❌ *সিরিয়াল {i+1}: ব্যর্থ*\n👤 অ্যাকাউন্ট: `{username}`\n⚠️ কারণ: {reason}"
            )
            
        time.sleep(5)

    await update.message.reply_text("✨ প্রসেসিং সম্পন্ন হয়েছে!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ বাতিল করা হয়েছে।")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return

    t = Thread(target=run_flask)
    t.start()

    application = ApplicationBuilder().token(token).build()
    application.post_init = set_bot_commands

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('restart', restart_bot),
            MessageHandler(filters.Regex('^(🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন|বট রিস্টার্ট)$'), start_extraction)
        ],
        states={
            GET_USERNAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_usernames)],
            GET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
            GET_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa_and_process)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
