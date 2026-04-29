import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from threading import Thread

# --- RENDER KEEP-ALIVE SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running and healthy!"

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_web).start()

# --- CONFIGURATION (Environment Variables) ---
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

# Temporary storage for admin adding channel
admin_temp = {}

# --- ADMIN: ADD CHANNEL (SIMPLE STEP-BY-STEP) ---
@bot.message_handler(commands=['addchannel'], func=lambda m: m.from_user.id == ADMIN_ID)
def add_channel_simple(message):
    admin_temp[ADMIN_ID] = {"step": "channel_id"}
    bot.send_message(ADMIN_ID, "📢 *Add New Channel*\n\nSend the channel's **username** (with @) or **channel ID** (numeric).\n\nExample: `@myvipchannel` or `-100123456789`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and not m.text.startswith('/') and ADMIN_ID in admin_temp)
def handle_admin_input(message):
    state = admin_temp[ADMIN_ID]
    step = state["step"]
    
    if step == "channel_id":
        ch_input = message.text.strip()
        try:
            if ch_input.startswith('@'):
                chat = bot.get_chat(ch_input)
                ch_id = chat.id
                ch_name = chat.title
            else:
                ch_id = int(ch_input)
                chat = bot.get_chat(ch_id)
                ch_name = chat.title
            admin_temp[ADMIN_ID] = {"step": "plan_duration", "channel_id": ch_id, "channel_name": ch_name, "plans": {}}
            bot.send_message(ADMIN_ID, f"✅ Channel detected: *{ch_name}*\n\nNow add plans.\n\nSend **duration in minutes** for Plan 1 (e.g., `1440` for 1 day, `43200` for 30 days, `0` for lifetime):", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Invalid channel. Make sure bot is admin and the channel is correct.\nError: {e}")
            del admin_temp[ADMIN_ID]
    
    elif step == "plan_duration":
        try:
            duration = int(message.text.strip())
            admin_temp[ADMIN_ID]["current_duration"] = duration
            admin_temp[ADMIN_ID]["step"] = "plan_price"
            bot.send_message(ADMIN_ID, f"Duration: {duration} minutes.\nSend **price** in ₹ (e.g., `99`):")
        except:
            bot.send_message(ADMIN_ID, "❌ Send a valid number (minutes).")
    
    elif step == "plan_price":
        try:
            price = int(message.text.strip())
            duration = admin_temp[ADMIN_ID]["current_duration"]
            admin_temp[ADMIN_ID]["plans"][str(duration)] = str(price)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("➕ Add Another Plan", callback_data="add_more_plan"))
            markup.add(InlineKeyboardButton("✅ Save Channel", callback_data="save_channel"))
            bot.send_message(ADMIN_ID, f"✅ Plan {duration} mins = ₹{price} added.\n\nWhat next?", reply_markup=markup)
            admin_temp[ADMIN_ID]["step"] = "waiting_for_more_or_save"
        except:
            bot.send_message(ADMIN_ID, "❌ Send a valid price (integer).")
    
    elif step == "waiting_for_more_or_save":
        # handled by callback
        pass

@bot.callback_query_handler(func=lambda call: call.data in ["add_more_plan", "save_channel"] and call.from_user.id == ADMIN_ID)
def handle_add_more(call):
    if call.data == "add_more_plan":
        admin_temp[ADMIN_ID]["step"] = "plan_duration"
        bot.edit_message_text("Send **duration in minutes** for next plan:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    elif call.data == "save_channel":
        data = admin_temp.pop(ADMIN_ID)
        ch_id = data["channel_id"]
        ch_name = data["channel_name"]
        plans = data["plans"]
        
        channels_col.update_one({"channel_id": ch_id}, {"$set": {"name": ch_name, "plans": plans, "admin_id": ADMIN_ID}}, upsert=True)
        bot_username = bot.get_me().username
        invite_link = f"https://t.me/{bot_username}?start={ch_id}"
        bot.send_message(ADMIN_ID, f"✅ *Channel saved successfully!*\n\nName: {ch_name}\nPlans: {plans}\n\nUser join link:\n`{invite_link}`", parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# --- OTHER ADMIN COMMANDS (unchanged) ---
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    text = message.text.split()

    if len(text) > 1:
        try:
            ch_id = int(text[1])
            ch_data = channels_col.find_one({"channel_id": ch_id})
            if ch_data:
                markup = InlineKeyboardMarkup()
                for p_time, p_price in ch_data['plans'].items():
                    label = f"Lifetime" if p_time == "0" else (f"{p_time} Min" if int(p_time) < 60 else f"{int(p_time)//1440} Days")
                    markup.add(InlineKeyboardButton(f"💳 {label} - ₹{p_price}", callback_data=f"select_{ch_id}_{p_time}"))
                markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
                bot.send_message(message.chat.id, 
                    f"Welcome!\n\nYou are joining: *{ch_data['name']}*.\n\nPlease select a subscription plan below:", 
                    reply_markup=markup, parse_mode="Markdown")
                return
        except:
            pass

    if user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "✅ Admin Panel Active!\n\n/addchannel - Add/Edit Channel\n/channels - Manage Existing Channels")
    else:
        bot.send_message(message.chat.id, "Welcome! To join a channel, please use the link provided by the Admin.")

@bot.message_handler(commands=['channels'], func=lambda m: m.from_user.id == ADMIN_ID)
def list_channels(message):
    markup = InlineKeyboardMarkup()
    cursor = channels_col.find({"admin_id": ADMIN_ID})
    count = 0
    for ch in cursor:
        markup.add(InlineKeyboardButton(f"📢 {ch['name']}", callback_data=f"manage_{ch['channel_id']}"))
        count += 1
    markup.add(InlineKeyboardButton("➕ Add New Channel", callback_data="add_new_simple"))
    if count == 0:
        bot.send_message(ADMIN_ID, "No channels found. Click below to add one.", reply_markup=markup)
    else:
        bot.send_message(ADMIN_ID, "Your Managed Channels:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_new_simple" and call.from_user.id == ADMIN_ID)
def add_new_simple_cb(call):
    bot.answer_callback_query(call.id)
    add_channel_simple(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_') and call.from_user.id == ADMIN_ID)
def manage_ch(call):
    ch_id = int(call.data.split('_')[1])
    ch_data = channels_col.find_one({"channel_id": ch_id})
    if not ch_data:
        bot.edit_message_text("Channel not found.", call.message.chat.id, call.message.message_id)
        return
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={ch_id}"
    bot.edit_message_text(f"Settings for: *{ch_data['name']}*\n\nYour Link: `{link}`\n\nTo edit plans, use /addchannel and add the channel again (same ID will overwrite).", 
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- USER PAYMENT FLOW ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
def user_pays(call):
    _, ch_id, mins = call.data.split('_')
    ch_id = int(ch_id)
    mins = str(mins)
    ch_data = channels_col.find_one({"channel_id": ch_id})
    if not ch_data or mins not in ch_data['plans']:
        bot.answer_callback_query(call.id, "Plan not available. Please contact admin.")
        return
    price = ch_data['plans'][mins]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}%26am={price}%26cu=INR"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_{ch_id}_{mins}"))
    markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    label = "Lifetime" if mins == "0" else f"{mins} Minutes"
    bot.send_photo(call.message.chat.id, qr_url, 
                   caption=f"Plan: {label}\nPrice: ₹{price}\nUPI ID: `{UPI_ID}`\n\nPlease complete the payment and click 'I Have Paid'.", 
                   reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('paid_'))
def admin_notify(call):
    _, ch_id, mins = call.data.split('_')
    ch_id = int(ch_id)
    mins = str(mins)
    user = call.from_user
    ch_data = channels_col.find_one({"channel_id": ch_id})
    if not ch_data:
        bot.answer_callback_query(call.id, "Channel config missing. Contact admin.")
        return
    price = ch_data['plans'][mins]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{ch_id}_{mins}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}"))
    label = "Lifetime" if mins == "0" else f"{mins} Mins"
    bot.send_message(ADMIN_ID, f"🔔 *Payment Verification Required!*\n\nUser: {user.first_name}\nChannel: {ch_data['name']}\nPlan: {label}\nPrice: ₹{price}", 
                     reply_markup=markup, parse_mode="Markdown")
    u_markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    bot.send_message(call.message.chat.id, "✅ Your payment request has been sent. Please wait for Admin approval.", reply_markup=u_markup)

# --- APPROVAL & EXPIRY ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('app_'))
def approve_now(call):
    _, u_id, ch_id, mins = call.data.split('_')
    u_id, ch_id, mins = int(u_id), int(ch_id), int(mins)
    try:
        ch_data = channels_col.find_one({"channel_id": ch_id})
        if not ch_data:
            bot.send_message(ADMIN_ID, "Channel not found.")
            return
        if mins == 0:
            # Lifetime subscription
            link = bot.create_chat_invite_link(ch_id, member_limit=1)
            expiry_text = "Lifetime (never expires)"
            users_col.update_one({"user_id": u_id, "channel_id": ch_id}, 
                                 {"$set": {"expiry": None, "lifetime": True}}, upsert=True)
        else:
            expiry_datetime = datetime.now() + timedelta(minutes=mins)
            expiry_ts = int(expiry_datetime.timestamp())
            link = bot.create_chat_invite_link(ch_id, member_limit=1, expire_date=expiry_ts)
            expiry_text = f"{mins} minutes"
            users_col.update_one({"user_id": u_id, "channel_id": ch_id}, 
                                 {"$set": {"expiry": expiry_ts}}, upsert=True)
        bot.send_message(u_id, f"🥳 *Payment Approved!*\n\nSubscription: {expiry_text}\n\nJoin Link: {link.invite_link}\n\n⚠️ Keep this link safe. It will expire after the subscription period." if mins != 0 else f"🥳 *Payment Approved!*\n\nSubscription: Lifetime\n\nJoin Link: {link.invite_link}\n\nYou have permanent access.", parse_mode="Markdown")
        bot.edit_message_text(f"✅ Approved user {u_id} for {expiry_text}.", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('rej_'))
def reject_now(call):
    _, u_id = call.data.split('_')
    u_id = int(u_id)
    bot.send_message(u_id, "❌ Your payment was rejected. Please contact admin for support.")
    bot.edit_message_text(f"❌ Rejected user {u_id}.", call.message.chat.id, call.message.message_id)

# --- AUTOMATIC EXPIRY KICK (Lifetime users excluded) ---
def kick_expired_users():
    now = datetime.now().timestamp()
    # Find users with expiry set and expired
    expired_users = users_col.find({"expiry": {"$ne": None, "$lte": now}})
    bot_username = bot.get_me().username
    for user in expired_users:
        try:
            bot.ban_chat_member(user['channel_id'], user['user_id'])
            bot.unban_chat_member(user['channel_id'], user['user_id'])
            rejoin_url = f"https://t.me/{bot_username}?start={user['channel_id']}"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Re-join / Renew", url=rejoin_url))
            bot.send_message(user['user_id'], "⚠️ Your subscription has expired.\n\nTo join again or renew, please click the button below:", reply_markup=markup)
            users_col.delete_one({"_id": user['_id']})
        except Exception as e:
            print(f"Kick error: {e}")

# --- STARTUP ---
if __name__ == '__main__':
    keep_alive()
    scheduler = BackgroundScheduler()
    scheduler.add_job(kick_expired_users, 'interval', minutes=1)
    scheduler.start()
    bot.remove_webhook()
    print("Bot is running with new simple channel add system...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
