import os
import threading
import pyotp
from flask import Flask
from instagrapi import Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Free server keeping-alive setup
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Fetch Bot Token from environment variable
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🤖 **Instagram Cookie Extractor Bot**\n\n"
        "একাউন্ট লিস্ট নিচে দেওয়া ফরম্যাটে পাঠান:\n"
        "`username|password|2fa_secret`\n\n"
        "উদাহরণ:\n"
        "`user1|pass123|JBSWY3DPEHPK3PXP`\n"
        "`user2|pass456`"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def extract_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 প্রসেসিং শুরু হয়েছে, অনুগ্রহ করে অপেক্ষা করুন...")
    raw_lines = update.message.text.strip().split('\n')
    results = []
    
    for line in raw_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        try:
            parts = line_clean.split('|')
            user = parts[0].strip()
            pwd = parts[1].strip()
            two_fa = parts[2].strip() if len(parts) > 2 else None
            
            cl = Client()
            
            # Auto 2FA login handling
            if two_fa:
                totp = pyotp.TOTP(two_fa.replace(" ", ""))
                code = totp.now()
                cl.login(user, pwd, verification_code=code)
            else:
                cl.login(user, pwd)
                
            session = cl.get_settings()
            csrftoken = session['cookies'].get('csrftoken', '')
            sessionid = session['cookies'].get('sessionid', '')
            
            cookie_str = f"csrftoken={csrftoken}; sessionid={sessionid}"
            results.append(f"{user}|{pwd}|{cookie_str}")
            
        except Exception as e:
            results.append(f"{line_clean} | Failed: {str(e)}")

    output_text = "\n".join(results)
    file_path = "official_IG_Cookies.txt"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output_text)
        
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
    await update.message.reply_document(
        document=open(file_path, "rb"),
        caption="✅ আপনার একাউন্টের কুকিজ তৈরি সম্পন্ন হয়েছে!"
    )

if __name__ == '__main__':
    # Start web server in background for free hosting
    threading.Thread(target=run_flask).start()
    
    # Start Telegram bot
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, extract_cookies))
    bot_app.run_polling()