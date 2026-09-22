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

# States for ConversationHandler
GET_USERNAMES, GET_PASSWORD, GET_2FA = range(3)
user_data_store = {}

# Keep-alive Flask server for Railway/Hosting
app = Flask('')

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# টেলিগ্রাম থ্রি-ডট মেনু বা কমান্ড সেট করা
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "বট চালু করুন"),
        BotCommand("restart", "বট রিস্টার্ট করুন")
    ]
    await application.bot.set_my_commands(commands)

# /start অথবা রিস্টার্ট হ্যান্ডলার
async def start_or_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store.pop(user_id)
        
    keyboard = [[KeyboardButton("🚀 কুকিজ এক্সট্রাক্ট করা শুরু করুন")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🤖 *ইনস্টাগ্রাম কুকি এক্সট্রাক্টর বটে স্বাগতম!*\n\n"
        "যেকোনো সময় নতুন করে শুরু করতে চাইলে নিচের বাটনে চাপ দিন অথবা বাম পাশের মেনু থেকে `/restart` সিলেক্ট করুন।",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# এক্সট্রাকশন প্রসেস শুরু
async def start_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *ধাপ ১ / ৩ — ইউজারনেম দিন*\n\n"
        "যে অ্যাকাউন্টগুলোর কুকিজ বের করবেন, সেগুলোর ইনস্টাগ্রাম ইউজারনেম দিন।\n"
        "(একাধিক হলে প্রতি লাইনে একটি করে লিখুন):\n\n"
        "`user1`\n`user2`\n`user3`",
        parse_mode="Markdown"
    )
    return GET_USERNAMES

# ইউজারনেম রিসিভ ও ভ্যালিডেশন
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

# মূল লগইন এবং কুকিজ এক্সট্রাকশন লজিক (রিয়েল ভ্যালিডেশন সহ)
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

    await update.message.reply_text("🔄 অ্যাকাউন্টগুলো ইনস্টাগ্রাম সার্ভারে রিয়েল-টাইম চেক করা হচ্ছে, একটু অপেক্ষা করুন...")

    for i, username in enumerate(usernames):
        tfa_key = keys[i]
        cl = Client()
        
        # ইনস্টাগ্রামের অফিসিয়াল অ্যান্ড্রয়েড ডিভাইস ও ইউজার এজেন্ট
        cl.set_user_agent("Instagram 300.0.0.25.112 Android (31/12; 480dpi; 1080x2340; Samsung; Galaxy S21; SM-G991B; exynos2100; en_US; 452345121)")
        try:
            cl.set_device({
                "app_version": "300.0.0.25.112",
                "android_version": 31,
                "android_release": "12",
                "dpi": "480dpi",
                "resolution": "1080x2340",
                "manufacturer": "Samsung",
                "device": "Galaxy S21",
                "model": "SM-G991B",
                "cpu": "exynos2100"
            })
        except Exception:
            pass

        cl.delay_range = [3, 6]
        
        try:
            # আগে চেক করা ইউজারনেমটি ইনস্টাগ্রামে আদৌ ভ্যালিড কি না
            try:
                user_id_ig = cl.user_id_from_username(username)
                if not user_id_ig:
                    raise Exception("invalid_user")
            except Exception:
                await update.message.reply_text(
                    f"❌ *সিরিয়াল {i+1}: ভুল ইউজারনেম*\n"
                    f"👤 ইউজারনেম: `{username}`\n"
                    f"⚠️ কারণ: ইনস্টাগ্রামে এই নামের কোনো ভ্যালিড অ্যাকাউন্ট খুঁজে পাওয়া যায়নি।",
                    parse_mode="Markdown"
                )
                continue

            # TOTP কোড জেনারেট করা
            totp_code = pyotp.TOTP(tfa_key.replace(" ", "")).now()
            
            # রিয়েল লগইন রিকোয়েস্ট পাঠানো
            login_success = cl.login(username, password, verification_code=totp_code)
            
            if login_success:
                cookies = cl.get_settings()
                
                # ফাইলে কুকিজ সেভ করা
                filename = f"cookie_{username}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(json.dumps(cookies, indent=4))
                
                # ফাইল আকারে চ্যাটে পাঠানো
                with open(filename, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"✅ *সিরিয়াল {i+1}: সফল!*\n👤 অ্যাকাউন্ট: `{username}`\n🍪 কুকিজ ফাইল সফলভাবে এক্সট্রাক্ট করা হয়েছে।"
                    )
                if os.path.exists(filename):
                    os.remove(filename)
            else:
                await update.message.reply_text(
                    f"❌ *সিরিয়াল {i+1}: লগইন ব্যর্থ*\n"
                    f"👤 ইউজারনেম: `{username}`\n"
                    f"📝 কারণ: পাসওয়ার্ড বা 2FA কি সঠিক নয়।",
                    parse_mode="Markdown"
                )
        except Exception as e:
            err_str = str(e).lower()
            if "bad password" in err_str or "invalid password" in err_str or "sentry_block" in err_str:
                reason = "পাসওয়ার্ড ভুল দেওয়া হয়েছে।"
            elif "two_factor" in err_str or "totp" in err_str or "code" in err_str:
                reason = "2FA কি (Secret Key) সঠিক নয় বা মেয়াদোত্তীর্ণ।"
            elif "checkpoint" in err_str or "challenge" in err_str:
                reason = "অ্যাকাউন্টটি ইনস্টাগ্রাম সিকিউরিটি চেকপয়েন্টে (Checkpoint) আটকে আছে। এটি ব্রাউজারে লগইন করে ঠিক করতে হবে।"
            elif "invalid_user" in err_str or "user_id_from_username" in err_str:
                reason = "ইনস্টাগ্রামে এই অ্যাকাউন্টটি অস্তিত্বহীন বা ডিলিট করা।"
            elif "wait" in err_str or "rate limit" in err_str or "please wait" in err_str:
                reason = "অতিরিক্ত চেষ্টার কারণে ইনস্টাগ্রাম সাময়িকভাবে রেট লিমিট করেছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"
            else:
                reason = f"লগইন ত্রুটি: {str(e)}"

            await update.message.reply_text(
                f"❌ *সিরিয়াল {i+1}: লগইন করা যায়নি*\n"
                f"👤 ইউজারনেম: `{username}`\n"
                f"⚠️ সুনির্দিষ্ট কারণ: {reason}",
                parse_mode="Markdown"
            )
            
        time.sleep(4) # আইপি থ্রটলিং এড়াতে বিরতি

    await update.message.reply_text("✨ সমস্ত অ্যাকাউন্টগুলোর প্রসেসিং শেষ! নতুন কাজ শুরু করতে মেনু থেকে /restart এ ক্লিক করুন।")
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
    application.post_init = set_bot_commands

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_or_restart),
            CommandHandler('restart', start_or_restart),
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
