import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, request, jsonify
from threading import Thread
from datetime import datetime, timedelta
import base64
from io import BytesIO

# ------------------ CONFIG ------------------
BOT_TOKEN = '8626144455:AAE4OmHD5UW_hQdcTL9ZgeieW0gLHcFMjvk'
ADMIN_ID = 1924277344
UPI_ID = 'vipseller@nyes'
CONTACT_USERNAME = 'your_username'  # Apna username daalo
MINI_APP_URL = os.getenv('MINI_APP_URL', 'https://your-site.netlify.app')

bot = telebot.TeleBot(BOT_TOKEN)

# Hardcoded plans (directly dikhenge)
PLANS = [
    {"name": "🔥 10 Groups", "price": 199, "channel_id": 1, "duration": 1440},
    {"name": "⚡ 20 Groups", "price": 249, "channel_id": 2, "duration": 2880},
    {"name": "✨ 30 Groups", "price": 299, "channel_id": 3, "duration": 4320},
    {"name": "💎 50 Groups", "price": 349, "channel_id": 4, "duration": 7200},
    {"name": "👑 100 Groups", "price": 399, "channel_id": 5, "duration": 14400},
    {"name": "🏆 150 Groups", "price": 449, "channel_id": 6, "duration": 21600},
    {"name": "🦁 200 Groups", "price": 499, "channel_id": 7, "duration": 28800},
    {"name": "❇️ All in one pack", "price": 999, "channel_id": 8, "duration": 0}
]

# ------------------ FLASK API ------------------
flask_app = Flask(__name__)

@flask_app.route('/plans', methods=['GET'])
def get_plans():
    return jsonify(PLANS)

@flask_app.route('/submit_payment', methods=['POST'])
def submit_payment():
    try:
        data = request.json
        user_id = data.get('user_id')
        plan_name = data.get('plan_name')
        price = data.get('price')
        screenshot_base64 = data.get('screenshot')
        
        # Notify admin
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{plan_name}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        )
        
        bot.send_message(
            ADMIN_ID,
            f"🔔 New Payment!\n\nUser ID: {user_id}\nPlan: {plan_name}\nAmount: ₹{price}",
            reply_markup=markup
        )
        
        if screenshot_base64:
            img_data = base64.b64decode(screenshot_base64)
            bot.send_photo(ADMIN_ID, photo=BytesIO(img_data), caption="Payment Screenshot")
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)

# ------------------ BOT COMMANDS ------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛒 Open VIP Store", web_app=WebAppInfo(url=MINI_APP_URL)))
    markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    
    bot.send_message(
        message.chat.id,
        "🌟 *Welcome to VIP Store* 🌟\n\nClick below to browse plans:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_payment(call):
    _, user_id, plan_name = call.data.split('_', 2)
    bot.send_message(
        int(user_id),
        f"🎉 *Payment Approved!*\n\nYour plan '{plan_name}' is active!\n\nJoin link: https://t.me/your_channel",
        parse_mode="Markdown"
    )
    bot.edit_message_text("✅ Approved", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Approved!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_payment(call):
    _, user_id = call.data.split('_', 1)
    bot.send_message(int(user_id), "❌ Payment rejected. Please contact admin.")
    bot.edit_message_text("❌ Rejected", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Rejected!")

# ------------------ MAIN ------------------
if __name__ == "__main__":
    # Start Flask in background
    Thread(target=run_flask, daemon=True).start()
    # Start bot
    print("Bot started! Plans are hardcoded and will show in Mini App.")
    bot.infinity_polling(timeout=20)
