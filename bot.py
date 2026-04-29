import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from threading import Thread

# ------------------ KEEP ALIVE SERVER (for Render) ------------------
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_web).start()

# ------------------ CONFIGURATION ------------------
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
UPI_ID = os.getenv('UPI_ID')
CONTACT_USERNAME = os.getenv('CONTACT_USERNAME')

bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['sub_management']
channels_col = db['channels']
users_col = db['users']

# Temporary storage for admin session
admin_temp = {}

# ------------------ ADMIN: ADD CHANNEL (SIMPLE) ------------------
@bot.message_handler(commands=['addchannel'])
def add_channel_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    admin_temp[ADMIN_ID] = {"step": "channel_id"}
    bot.send_message(ADMIN_ID, 
        "📢 *Add New Channel*\n\n"
        "Send the channel **username** (with @) or **channel ID** (numeric).\n"
        "Example: `@myvipchannel` or `-100123456789`",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and not m.text.startswith('/') and ADMIN_ID in admin_temp)
def add_channel_step2(m):
    state = admin_temp[ADMIN_ID]
    step = state["step"]
    text = m.text.strip()

    if step == "channel_id":
        # Detect channel
        try:
            if text.startswith('@'):
                chat = bot.get_chat(text)
            else:
                chat = bot.get_chat(int(text))
            ch_id = chat.id
            ch_name = chat.title
            admin_temp[ADMIN_ID] = {
                "step": "plan_duration",
                "channel_id": ch_id,
                "channel_name": ch_name,
                "plans": {}
            }
            bot.send_message(ADMIN_ID,
                f"✅ Channel: *{ch_name}* (ID: `{ch_id}`)\n\n"
                "Now add plans.\n\nSend **duration in minutes** for Plan 1.\n"
                "Examples: `1440` (1 day), `43200` (30 days), `0` (Lifetime)",
                parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Error: {e}\n\nMake sure bot is admin in the channel and the username/ID is correct.")
            del admin_temp[ADMIN_ID]

    elif step == "plan_duration":
        try:
            duration = int(text)
            admin_temp[ADMIN_ID]["current_duration"] = duration
            admin_temp[ADMIN_ID]["step"] = "plan_price"
            bot.send_message(ADMIN_ID, f"Duration: {duration} minutes.\nNow send **price** in ₹ (e.g., `99`):")
        except:
            bot.send_message(ADMIN_ID, "❌ Please send a valid number (minutes).")

    elif step == "plan_price":
        try:
            price = int(text)
            duration = admin_temp[ADMIN_ID]["current_duration"]
            admin_temp[ADMIN_ID]["plans"][str(duration)] = str(price)
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("➕ Add another plan", callback_data="add_more_plan"),
                InlineKeyboardButton("✅ Save channel", callback_data="save_channel")
            )
            bot.send_message(ADMIN_ID, f"✅ Plan added: {duration} min = ₹{price}\n\nWhat now?", reply_markup=markup)
            admin_temp[ADMIN_ID]["step"] = "waiting"
        except:
            bot.send_message(ADMIN_ID, "❌ Send a valid price (integer).")

    elif step == "waiting":
        # Handled by callback
        pass

@bot.callback_query_handler(func=lambda call: call.from_user.id == ADMIN_ID and call.data in ["add_more_plan", "save_channel"])
def handle_plan_callback(call):
    if call.data == "add_more_plan":
        admin_temp[ADMIN_ID]["step"] = "plan_duration"
        bot.edit_message_text("Send duration (in minutes) for the next plan:", call.message.chat.id, call.message.message_id)
    elif call.data == "save_channel":
        if ADMIN_ID not in admin_temp:
            bot.answer_callback_query(call.id, "Session expired. Use /addchannel again.")
            return
        data = admin_temp.pop(ADMIN_ID)
        ch_id = data["channel_id"]
        ch_name = data["channel_name"]
        plans = data["plans"]
        # Save to MongoDB
        channels_col.update_one(
            {"channel_id": ch_id},
            {"$set": {"name": ch_name, "plans": plans, "admin_id": ADMIN_ID}},
            upsert=True
        )
        bot_username = bot.get_me().username
        invite_link = f"https://t.me/{bot_username}?start={ch_id}"
        bot.send_message(ADMIN_ID,
            f"✅ *Channel saved successfully!*\n\n"
            f"📢 Name: {ch_name}\n"
            f"🆔 ID: {ch_id}\n"
            f"📋 Plans: {plans}\n\n"
            f"🔗 User join link:\n`{invite_link}`",
            parse_mode="Markdown")
        bot.edit_message_text("✅ Channel saved.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# ------------------ LIST CHANNELS ------------------
@bot.message_handler(commands=['channels'])
def list_channels(m):
    if m.from_user.id != ADMIN_ID:
        return
    markup = InlineKeyboardMarkup()
    for ch in channels_col.find({"admin_id": ADMIN_ID}):
        markup.add(InlineKeyboardButton(f"📢 {ch['name']}", callback_data=f"manage_{ch['channel_id']}"))
    markup.add(InlineKeyboardButton("➕ Add Channel", callback_data="add_new_simple"))
    bot.send_message(ADMIN_ID, "Your Channels:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_new_simple" and call.from_user.id == ADMIN_ID)
def add_new_cb(call):
    bot.answer_callback_query(call.id)
    add_channel_cmd(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_") and call.from_user.id == ADMIN_ID)
def manage_channel(call):
    ch_id = int(call.data.split("_")[1])
    ch = channels_col.find_one({"channel_id": ch_id})
    if not ch:
        bot.edit_message_text("Channel not found.", call.message.chat.id, call.message.message_id)
        return
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={ch_id}"
    bot.edit_message_text(
        f"*{ch['name']}*\n\n"
        f"📌 Join link:\n`{link}`\n\n"
        f"📋 Plans: {ch['plans']}\n\n"
        f"To edit, use /addchannel and add the same channel again (it will overwrite).",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown")

# ------------------ USER START ------------------
@bot.message_handler(commands=['start'])
def start_cmd(m):
    user_id = m.from_user.id
    args = m.text.split()
    if len(args) > 1:
        try:
            ch_id = int(args[1])
            ch_data = channels_col.find_one({"channel_id": ch_id})
            if ch_data:
                markup = InlineKeyboardMarkup()
                for dur, price in ch_data['plans'].items():
                    if dur == "0":
                        label = "💎 Lifetime"
                    else:
                        d = int(dur)
                        if d < 60:
                            label = f"{d} Min"
                        else:
                            days = d // 1440
                            label = f"{days} Days"
                    markup.add(InlineKeyboardButton(f"{label} - ₹{price}", callback_data=f"buy_{ch_id}_{dur}"))
                markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
                bot.send_message(m.chat.id,
                    f"✨ *Welcome to {ch_data['name']}* ✨\n\nChoose your plan:",
                    reply_markup=markup, parse_mode="Markdown")
                return
        except: pass
    if user_id == ADMIN_ID:
        bot.send_message(m.chat.id, "✅ Admin Panel\n\n/addchannel - Add channel\n/channels - Manage channels")
    else:
        bot.send_message(m.chat.id, "Welcome! Use the link provided by admin to join.")

# ------------------ PAYMENT FLOW ------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def show_payment(call):
    _, ch_id, dur = call.data.split("_")
    ch_id = int(ch_id)
    dur = str(dur)
    ch_data = channels_col.find_one({"channel_id": ch_id})
    if not ch_data or dur not in ch_data['plans']:
        bot.answer_callback_query(call.id, "Plan expired. Contact admin.")
        return
    price = ch_data['plans'][dur]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}&am={price}&cu=INR"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ I have paid", callback_data=f"paid_{ch_id}_{dur}"))
    markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    plan_label = "Lifetime" if dur == "0" else f"{dur} minutes"
    bot.send_photo(call.message.chat.id, qr_url,
        caption=f"💳 *Plan:* {plan_label}\n💰 *Price:* ₹{price}\n📲 *UPI ID:* `{UPI_ID}`\n\nScan QR or pay to above ID, then click 'I have paid'.",
        reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def payment_received(call):
    _, ch_id, dur = call.data.split("_")
    ch_id = int(ch_id)
    user = call.from_user
    ch_data = channels_col.find_one({"channel_id": ch_id})
    if not ch_data:
        bot.answer_callback_query(call.id, "Error. Contact admin.")
        return
    price = ch_data['plans'][dur]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{ch_id}_{dur}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}"))
    bot.send_message(ADMIN_ID,
        f"🔔 *Payment Proof*\n👤 {user.first_name}\n📢 {ch_data['name']}\n⏱ {dur} min\n₹{price}",
        reply_markup=markup, parse_mode="Markdown")
    bot.send_message(call.message.chat.id, "✅ Request sent! Admin will verify shortly.")
    bot.answer_callback_query(call.id)

# ------------------ APPROVE / REJECT ------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve(call):
    _, uid, chid, dur = call.data.split("_")
    uid, chid = int(uid), int(chid)
    dur = int(dur)
    try:
        if dur == 0:
            link = bot.create_chat_invite_link(chid, member_limit=1)
            expiry_msg = "Lifetime access"
            users_col.update_one({"user_id": uid, "channel_id": chid}, {"$set": {"expiry": None}}, upsert=True)
        else:
            expire_date = datetime.now() + timedelta(minutes=dur)
            link = bot.create_chat_invite_link(chid, member_limit=1, expire_date=expire_date)
            expiry_msg = f"{dur} minutes"
            users_col.update_one({"user_id": uid, "channel_id": chid}, {"$set": {"expiry": expire_date.timestamp()}}, upsert=True)
        bot.send_message(uid, f"🎉 *Access Granted!*\n\nYour {expiry_msg} plan is active.\nJoin: {link.invite_link}")
        bot.edit_message_text("✅ Approved", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"Error approving: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def reject(call):
    uid = int(call.data.split("_")[1])
    bot.send_message(uid, "❌ Payment rejected. Contact admin.")
    bot.edit_message_text("❌ Rejected", call.message.chat.id, call.message.message_id)

# ------------------ EXPIRY KICK ------------------
def kick_expired():
    now = datetime.now().timestamp()
    expired = users_col.find({"expiry": {"$ne": None, "$lte": now}})
    for user in expired:
        try:
            bot.ban_chat_member(user['channel_id'], user['user_id'])
            bot.unban_chat_member(user['channel_id'], user['user_id'])
            bot.send_message(user['user_id'], "⚠️ Your subscription expired. Use /start or admin's link to renew.")
            users_col.delete_one({"_id": user['_id']})
        except:
            pass

# ------------------ MAIN ------------------
if __name__ == "__main__":
    keep_alive()
    scheduler = BackgroundScheduler()
    scheduler.add_job(kick_expired, 'interval', minutes=1)
    scheduler.start()
    bot.remove_webhook()
    print("Bot started with /addchannel system")
    bot.infinity_polling(timeout=20)
