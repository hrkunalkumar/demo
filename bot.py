# Temporary storage for admin adding channel
admin_temp = {}

@bot.message_handler(commands=['addchannel'], func=lambda m: m.from_user.id == ADMIN_ID)
def add_channel_simple(message):
    admin_temp[ADMIN_ID] = {"step": "channel_id"}
    bot.send_message(ADMIN_ID, "📢 *Add New Channel*\n\nSend the channel's **username** (with @) or **channel ID** (numeric).\n\nExample: `@myvipchannel` or `-100123456789`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and not m.text.startswith('/') and ADMIN_ID in admin_temp)
def handle_admin_input(message):
    state = admin_temp[ADMIN_ID]
    step = state["step"]
    print(f"DEBUG: step={step}, text={message.text}")  # Debug line (will appear in Render logs)
    
    if step == "channel_id":
        ch_input = message.text.strip()
        try:
            if ch_input.startswith('@'):
                chat = bot.get_chat(ch_input)
            else:
                # Try as integer ID
                ch_id_int = int(ch_input)
                chat = bot.get_chat(ch_id_int)
            ch_id = chat.id
            ch_name = chat.title
            admin_temp[ADMIN_ID] = {"step": "plan_duration", "channel_id": ch_id, "channel_name": ch_name, "plans": {}}
            bot.send_message(ADMIN_ID, f"✅ Channel detected: *{ch_name}*\nChannel ID: `{ch_id}`\n\nNow add plans.\n\nSend **duration in minutes** for Plan 1 (e.g., `1440` for 1 day, `43200` for 30 days, `0` for lifetime):", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Invalid channel. Make sure:\n1. Bot is admin in that channel.\n2. Username or ID is correct.\n\nError: {str(e)}")
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
        if ADMIN_ID not in admin_temp:
            bot.answer_callback_query(call.id, "Session expired, use /addchannel again.")
            return
        data = admin_temp.pop(ADMIN_ID)
        ch_id = data["channel_id"]
        ch_name = data["channel_name"]
        plans = data["plans"]
        
        # Save to MongoDB
        result = channels_col.update_one(
            {"channel_id": ch_id}, 
            {"$set": {"name": ch_name, "plans": plans, "admin_id": ADMIN_ID}}, 
            upsert=True
        )
        print(f"DEBUG: MongoDB update result: {result.modified_count}, {result.upserted_id}")  # Debug
        
        bot_username = bot.get_me().username
        invite_link = f"https://t.me/{bot_username}?start={ch_id}"
        bot.send_message(ADMIN_ID, f"✅ *Channel saved successfully!*\n\nName: {ch_name}\nChannel ID: {ch_id}\nPlans: {plans}\n\nUser join link:\n`{invite_link}`", parse_mode="Markdown")
        bot.edit_message_text(f"✅ Channel '{ch_name}' saved.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
