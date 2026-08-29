import os
import logging
import json
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from instagrapi import Client
import pyotp

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler
GET_USERNAMES, GET_PASSWORD, GET_2FA = range(3)

# In-memory session data storage per user
user_data_store = {}

# Keep-alive Flask server for hosting platforms
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# টেলিগ্রামের থ্রি-ডট মেনু বা কমান্ড লিস্ট সেট করার ফাংশন
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "বট চালু করুন"),
        BotCommand("restart", "বট রিস্টার্ট করুন")
    ]
    await application.bot.set_my_commands(commands)

# /start কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
        
    keyboard = [[KeyboardButton("🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🤖 *ইনস্টাগ্রাম কুকি এক্সট্রাক্টর বটে স্বাগতম!*\n\n"
        "যেকোনো সময় বট রিস্টার্ট করতে চাইলে বাম পাশের মেনু বা থ্রি-ডট থেকে `/restart` এ ক্লিক করুন।\n\n"
        "✨ কাজ শুরু করতে নিচের বাটনে চাপ দিন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# মেনু থেকে রিস্টার্ট করার কমান্ড
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
        
    keyboard = [[KeyboardButton("🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🔄 *বট সফলভাবে রিস্টার্ট করা হয়েছে!*\n\n"
        "নতুন করে কুকিজ বের করতে নিচের বাটনে চাপ দিন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# এক্সট্রাকশন শুরু করার ধাপ
async def start_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *ধাপ ১ / ৩ — ইউজারনেম দিন*\n\n"
        "যে অ্যাকাউন্টগুলোর কুকিজ বের করবেন, সেগুলোর ইনস্টাগ্রাম ইউজারনেম দিন।\n"
        "(একাধিক হলে প্রতি লাইনে একটি করে লিখুন):\n\n"
        "`user1`\n`user2`\n`user3`",
        parse_mode="Markdown"
    )
    return GET_USERNAMES

# ইউজারনেম রিসিভ করা
async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    usernames = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not usernames:
        await update.message.reply_text("⚠️ দয়া করে অন্তত একটি সঠিক ইউজারনেম দিন।")
        return GET_USERNAMES

    user_data_store[update.effective_user.id] = {"usernames": usernames}
    
    await update.message.reply_text(
        f"✅ *মোট {len(usernames)} টি ইউজারনেম পাওয়া গেছে!*\n\n"
        "🔑 *ধাপ ২ / ৩ — পাসওয়ার্ড দিন*\n"
        "সব অ্যাকাউন্টের জন্য কমন পাসওয়ার্ডটি এখানে লিখে পাঠান:",
        parse_mode="Markdown"
    )
    return GET_PASSWORD

# পাসওয়ার্ড রিসিভ করা
async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশনের মেয়াদ শেষ। দয়া করে মেনু থেকে /restart দিয়ে আবার শুরু করুন।")
        return ConversationHandler.END
        
    user_data_store[user_id]["password"] = password
    usernames = user_data_store[user_id]["usernames"]
    
    await update.message.reply_text(
        "✅ *পাসওয়ার্ড সেভ করা হয়েছে।*\n\n"
        f"🔐 *ধাপ ৩ / ৩ — 2FA রিকভারি কি (Key) দিন*\n"
        f"যে সিরিয়ালে ইউজারনেম দিয়েছেন, ঠিক একই সিরিয়ালে {len(usernames)} টি 2FA কি প্রতি লাইনে একটি করে দিন:",
        parse_mode="Markdown"
    )
    return GET_2FA

# 2FA কি নিয়ে প্রসেস করা এবং ফাইল আকারে কুকিজ পাঠানো
async def receive_2fa_and_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    keys = [line.strip() for line in text.split('\n') if line.strip()]
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশনের মেয়াদ শেষ। মেনু থেকে /restart দিয়ে আবার শুরু করুন।")
        return ConversationHandler.END
        
    data = user_data_store[user_id]
    usernames = data["usernames"]
    password = data["password"]
    
    if len(keys) != len(usernames):
        await update.message.reply_text(f"⚠️ আপনি ইউজারনেম দিয়েছেন {len(usernames)} টি কিন্তু কি (Key) দিয়েছেন {len(keys)} টি। দয়া করে সঠিক সংখ্যায় কি দিন।")
        return GET_2FA

    await update.message.reply_text("🔄 অ্যাকাউন্টগুলো চেক করা হচ্ছে এবং কুকিজ ফাইল তৈরি হচ্ছে, একটু অপেক্ষা করুন...")

    for i, username in enumerate(usernames):
        tfa_key = keys[i]
        cl = Client()
        
        # সার্ভার আইপি ব্ল্যাকলিস্ট বা বট ডিটেক্ট এড়াতে রিয়েল ডিভাইস ও ইউজার-এজেন্ট সেট করা
        cl.set_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 287.0.0.28.104")
        cl.delay_range = [2, 5]  # রিকোয়েস্টগুলোর মাঝে নিরাপদ বিরতি
        
        try:
            totp_code = pyotp.TOTP(tfa_key.replace(" ", "")).now()
            login_success = cl.login(username, password, verification_code=totp_code)
            
            if login_success:
                cookies = cl.get_settings()
                
                # কুকিজ সুন্দর ফরম্যাটে টেক্সট ফাইলে সেভ করা
                filename = f"cookie_{username}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(json.dumps(cookies, indent=4))
                
                # সরাসরি ফাইল আকারে চ্যাটে পাঠিয়ে দেওয়া
                with open(filename, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"✅ *সিরিয়াল {i+1}: সফল!*\n👤 অ্যাকাউন্ট: `{username}`\n🍪 কুকিজ ফাইল নিচে দেওয়া হলো।"
                    )
                # লোকাল ফাইল মুছে ফেলা
                if os.path.exists(filename):
                    os.remove(filename)
            else:
                await update.message.reply_text(
                    f"❌ *সিরিয়াল {i+1}: ব্যর্থ*\n"
                    f"👤 ইউজারনেম: `{username}`\n"
                    f"📝 কারণ: পাসওয়ার্ড বা 2FA কোড সঠিক নয়।",
                    parse_mode="Markdown"
                )
        except Exception as e:
            err_str = str(e).lower()
            if "bad password" in err_str or "invalid password" in err_str:
                reason = "পাসওয়ার্ড ভুল দেওয়া হয়েছে।"
            elif "two_factor" in err_str or "totp" in err_str or "code" in err_str:
                reason = "2FA কি (Key) ভুল বা মেয়াদোত্তীর্ণ।"
            elif "checkpoint" in err_str or "challenge" in err_str:
                reason = "ইনস্টাগ্রাম অ্যাকাউন্ট সিকিউরিটি চেকপয়েন্টে (Checkpoint) আটকে গেছে।"
            elif "blacklist" in err_str or "ip" in err_str or "email" in err_str or "connection" in err_str:
                reason = "সার্ভার আইপি (IP) ইনস্টাগ্রামের ব্ল্যাকলিস্টে রয়েছে বা অতিরিক্ত রিকোয়েস্টের কারণে ব্লক করেছে।"
            elif "wait" in err_str or "rate limit" in err_str:
                reason = "অতিরিক্ত চেষ্টার কারণে ইনস্টাগ্রাম সাময়িকভাবে ব্লক করেছে (Rate Limit)।"
            else:
                reason = f"টেকনিক্যাল সমস্যা: {str(e)}"

            await update.message.reply_text(
                f"❌ *সিরিয়াল {i+1}: সমস্যা দেখা দিয়েছে*\n"
                f"👤 ইউজারনেম: `{username}`\n"
                f"⚠️ সুনির্দিষ্ট কারণ: {reason}",
                parse_mode="Markdown"
            )

    await update.message.reply_text("✨ সমস্ত অ্যাকাউন্টগুলোর প্রসেসিং শেষ! নতুন কাজ শুরু করতে থ্রি-ডট মেনু থেকে /restart এ ক্লিক করুন።")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
    await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে। নতুন করে শুরু করতে মেনু থেকে /restart ব্যবহার করুন।")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    t = Thread(target=run_flask)
    t.start()

    application = ApplicationBuilder().token(token).build()
    
    # থ্রি-ডট মেনুতে কমান্ড সেট করার জন্য হুক যুক্ত করা হলো
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
