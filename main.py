import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

# /start command (বট রিস্টার্ট করার জন্যও এটি ব্যবহার করা যাবে)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚀 Start Extracting Cookies")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🤖 *Instagram Cookie Extractor Bot*\n\n"
        "বট সফলভাবে রি-স্টার্ট বা শুরু হয়েছে। কুকিজ এক্সট্রাক্ট করতে নিচের বাটনে চাপ দিন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# Start extraction flow
async def start_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *ধাপ ১ / ৩* — ইনস্টাগ্রাম ইউজারনেম দিন।\n\n"
        "একটি হলে এভাবে:\n`username123`\n\n"
        "একাধিক হলে প্রতি লাইনে একটি করে দিন:\n`user1`\n`user2`\n`user3`",
        parse_mode="Markdown"
    )
    return GET_USERNAMES

# Receive usernames
async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    usernames = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not usernames:
        await update.message.reply_text("⚠️ দয়া করে অন্তত একটি সঠিক ইউজারনেম দিন।")
        return GET_USERNAMES

    user_data_store[update.effective_user.id] = {"usernames": usernames}
    
    user_list_str = "\n".join([f"• {u}" for u in usernames])
    await update.message.reply_text(
        f"✅ *মোট {len(usernames)} টি ইউজারনেম পাওয়া গেছে:*\n{user_list_str}\n\n"
        "🔑 *ধাপ ২ / ৩* — সব অ্যাকাউন্টের জন্য সাধারণ পাসওয়ার্ডটি দিন:",
        parse_mode="Markdown"
    )
    return GET_PASSWORD

# Receive password
async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশন মেয়াদোত্তীর্ণ হয়ে গেছে। দয়া করে /start লিখে আবার শুরু করুন।")
        return ConversationHandler.END
        
    user_data_store[user_id]["password"] = password
    usernames = user_data_store[user_id]["usernames"]
    
    keys_guide = "\n".join([f"Key {i+1} ➔ {u}" for i, u in enumerate(usernames)])
    
    await update.message.reply_text(
        "✅ *পাসওয়ার্ড সেভ হয়েছে।*\n\n"
        f"🔐 *ধাপ ৩ / ৩* — এবার ক্রমানুসারে {len(usernames)} টি 2FA রিকভারি কি (Key) দিন:\n"
        "(প্রতি লাইনে একটি করে, ইউজারনেমের সিরিয়াল অনুযায়ী)\n\n"
        f"{keys_guide}",
        parse_mode="Markdown"
    )
    return GET_2FA

# Receive 2FA keys and process with detailed Bengali error reporting & clean cookie formatting
async def receive_2fa_and_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    keys = [line.strip() for line in text.split('\n') if line.strip()]
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ সেশন মেয়াদোত্তীর্ণ হয়ে গেছে। দয়া করে /start লিখে আবার শুরু করুন।")
        return ConversationHandler.END
        
    data = user_data_store[user_id]
    usernames = data["usernames"]
    password = data["password"]
    
    if len(keys) != len(usernames):
        await update.message.reply_text(f"⚠️ আপনি ইউজারনেম দিয়েছেন {len(usernames)} টি কিন্তু কি (Key) দিয়েছেন {len(keys)} টি। দয়া করে সঠিক সংখ্যায় কি দিন।")
        return GET_2FA

    await update.message.reply_text("🔄 অ্যাকাউন্টগুলো প্রসেস করা হচ্ছে এবং কুকিজ এক্সট্রাক্ট করা হচ্ছে, একটু অপেক্ষা করুন...")

    for i, username in enumerate(usernames):
        tfa_key = keys[i]
        cl = Client()
        try:
            totp_code = pyotp.TOTP(tfa_key.replace(" ", "")).now()
            login_success = cl.login(username, password, verification_code=totp_code)
            
            if login_success:
                cookies = cl.get_settings()
                # সুন্দর ফরম্যাটে কুকিজ এবং সফলতার মেসেজ
                await update.message.reply_text(
                    f"✨ *সিরিয়াল: {i+1} | সফল!*\n"
                    f"👤 ইউজারনেম: `{username}`\n\n"
                    f"🍪 *এক্সট্রাক্ট করা কুকিজ ফরম্যাট:*\n```json\n{cookies}\n```",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *সিরিয়াল: {i+1} | ব্যর্থ!*\n"
                    f"👤 ইউজারনেম: `{username}`\n"
                    f"📝 কারণ: পাসওয়ার্ড বা 2FA কোড সঠিক নয় অথবা অ্যাকাউন্ট লক করা আছে।",
                    parse_mode="Markdown"
                )
        except Exception as e:
            err_str = str(e).lower()
            # ইনস্টাগ্রামের বিভিন্ন এরর বাংলায় সুন্দর করে বুঝিয়ে দেওয়ার লজিক
            if "bad password" in err_str or "invalid password" in err_str:
                reason = "পাসওয়ার্ড ভুল রয়েছে।"
            elif "two_factor" in err_str or "totp" in err_str or "code" in err_str:
                reason = "2FA কি (Key) ভুল বা মেয়াদোত্তীর্ণ।"
            elif "checkpoint" in err_str or "challenge" in err_str:
                reason = "অ্যাকাউন্টটি ইনস্টাগ্রাম সিকিউরিটি চেকপয়েন্ট বা ভেরিফিকেশনে আটকে আছে।"
            elif "wait" in err_str or "rate limit" in err_str:
                reason = "অতিরিক্ত চেষ্টার কারণে ইনস্টাগ্রাম সাময়িকভাবে ব্লক করেছে (Rate Limit)।"
            else:
                reason = f"টেকনিক্যাল ত্রুটি: {str(e)}"

            await update.message.reply_text(
                f"❌ *সিরিয়াল: {i+1} | এরর!*\n"
                f"👤 ইউজারনেম: `{username}`\n"
                f"⚠️ সমস্যা: {reason}",
                parse_mode="Markdown"
            )

    await update.message.reply_text("🎉 সমস্ত অ্যাকাউন্টগুলোর প্রসেসিং সম্পন্ন হয়েছে!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে। নতুন করে শুরু করতে /start বা 'বট রিস্টার্ট' চাপুন।")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    t = Thread(target=run_flask)
    t.start()

    application = ApplicationBuilder().token(token).build()

    # বট মেনুতে বা থ্রি-ডট মেনুতে কমান্ড সেট করার জন্য টেলিগ্রামে স্বয়ংক্রিয়ভাবে কাজ করবে
    # আপনি টেলিগ্রামের BotFather-এ গিয়ে /setcommands দিয়ে 'restart - বট রিস্টার্ট' সেট করে নিতে পারেন।

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('restart', start), # বট রিস্টার্ট কমান্ড
            MessageHandler(filters.Regex('^(🚀 Start Extracting Cookies|বট রিস্টার্ট)$'), start_extraction)
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
