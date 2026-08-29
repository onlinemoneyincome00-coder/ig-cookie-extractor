import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
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

# Keep-alive Flask server for hosting platforms like Railway
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🚀 Start Extracting Cookies")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🤖 *Instagram Cookie Extractor Bot*\n\n"
        "This bot extracts session cookies from Instagram accounts.\n\n"
        "✨ Press the button below to get started.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Start extraction flow
async def start_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *Step 1 / 3* — Send the Instagram username(s).\n\n"
        "Single:\n`username123`\n\n"
        "Multiple (one per line):\n`user1`\n`user2`\n`user3`",
        parse_mode="Markdown"
    )
    return GET_USERNAMES

# Receive usernames
async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    usernames = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not usernames:
        await update.message.reply_text("⚠️ Please provide at least one valid username.")
        return GET_USERNAMES

    user_data_store[update.effective_user.id] = {"usernames": usernames}
    
    user_list_str = "\n".join([f"• {u}" for u in usernames])
    await update.message.reply_text(
        f"✅ *{len(usernames)} usernames received:*\n{user_list_str}\n\n"
        "🔑 *Step 2 / 3* — Send the password.\n(Single password shared across all accounts)",
        parse_mode="Markdown"
    )
    return GET_PASSWORD

# Receive password
async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ Session expired. Please send /start again.")
        return ConversationHandler.END
        
    user_data_store[user_id]["password"] = password
    usernames = user_data_store[user_id]["usernames"]
    
    keys_guide = "\n".join([f"Key {i+1} ➔ Username {u}" for i, u in enumerate(usernames)])
    
    await update.message.reply_text(
        "✅ *Password saved.*\n\n"
        f"🔐 *Step 3 / 3* — Send {len(usernames)} 2FA recovery keys.\n"
        "(One per line, same order as usernames)\n\n"
        f"{keys_guide}",
        parse_mode="Markdown"
    )
    return GET_2FA

# Receive 2FA keys and start extraction process with live chat error reporting
async def receive_2fa_and_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    keys = [line.strip() for line in text.split('\n') if line.strip()]
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        await update.message.reply_text("⚠️ Session expired. Please send /start again.")
        return ConversationHandler.END
        
    data = user_data_store[user_id]
    usernames = data["usernames"]
    password = data["password"]
    
    if len(keys) != len(usernames):
        await update.message.reply_text(f"⚠️ You provided {len(keys)} keys for {len(usernames)} accounts. Please send matching number of keys in correct order.")
        return GET_2FA

    await update.message.reply_text("🔄 Processing accounts and extracting cookies, please wait...")

    # Process each account sequentially and report results live in chat
    for i, username in enumerate(usernames):
        tfa_key = keys[i]
        cl = Client()
        try:
            # Generate 2FA code if key is valid
            totp_code = pyotp.TOTP(tfa_key.replace(" ", "")).now()
            
            # Attempt login
            login_success = cl.login(username, password, verification_code=totp_code)
            
            if login_success:
                cookies = cl.get_settings()
                # Send success and cookies directly in chat
                await update.message.reply_text(
                    f"✅ *Account {i+1} Success:* `{username}`\n\n"
                    f"Cookies:\n`{cookies}`",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *Account {i+1} Failed:* `{username}`\nReason: Invalid login or incorrect credentials.",
                    parse_mode="Markdown"
                )
        except Exception as e:
            # Report serial-wise error directly in chat as requested
            error_msg = str(e)
            await update.message.reply_text(
                f"❌ *Account {i+1} Error:* `{username}`\nDetails: {error_msg}",
                parse_mode="Markdown"
            )

    await update.message.reply_text("✨ All accounts processing finished!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    # Start Flask server in background thread
    t = Thread(target=run_flask)
    t.start()

    application = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^🚀 Start Extracting Cookies$'), start_extraction)
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
