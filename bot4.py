import os
import re
import json
import logging
import requests
from dotenv import load_dotenv
from flask import Flask, request
import telebot
from telebot import util
import sys

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    load_dotenv(".env")
    TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

MAX_LEN = 4096

# -------------------- ТЕКСТ --------------------
def convert_markdown_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    return text

def send_long_message(chat_id, text, parse_mode='HTML'):
    safe_text = convert_markdown_to_html(text or "")
    for part in util.smart_split(safe_text, MAX_LEN):
        bot.send_message(chat_id, part, parse_mode=parse_mode)

# -------------------- WEBHOOK --------------------
@app.route('/')
def index():
    return "bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    if update:
        bot.process_new_updates([update])
    return '', 200

# -------------------- ИСТОРИЯ --------------------
history_file = "history.json"
history = {}

if os.path.exists(history_file):
    with open(history_file, "r", encoding='utf-8') as f:
        history = json.load(f)

def save_history():
    with open(history_file, "w", encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

API_KEY = os.getenv('API_KEY')

def chat(user_id, text):
    if str(user_id) not in history:
        history[str(user_id)] = [{"role": "system","content": "Ты - помощник"}]

    history[str(user_id)].append({"role": "user", "content": text})

    url = "https://api.intelligence.io.solutions/api/v1/chat/completions"
    headers = {"Content-Type": "application/json","Authorization": f"Bearer {API_KEY}"}
    data = {"model": "deepseek-ai/DeepSeek-R1-0528","messages": history[str(user_id)]}

    response = requests.post(url, headers=headers, json=data)
    data = response.json()

    content = data['choices'][0]['message']['content']
    history[str(user_id)].append({"role": "assistant", "content": content})

    save_history()
    return content

# -------------------- БАЗА --------------------
db_path = "db.json"
db = {"users": {}}

if os.path.exists(db_path) and os.path.getsize(db_path) != 0:
    with open(db_path, "r", encoding='utf-8') as f:
        db = json.load(f)

def save_db():
    with open(db_path, "w", encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# -------------------- КОМАНДЫ --------------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id

    if user_id not in db["users"] or db["users"].get(user_id, {}).get("awaiting") == "name":
        db["users"][user_id] = {"awaiting": "name"}
        save_db()
        bot.send_message(user_id, "Напиши имя")
        return

    db["users"][user_id]["money"] = 20000
    save_db()

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Игровой автомат", "Игральный кубик")

    bot.send_message(user_id, "Привет", reply_markup=keyboard)

@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    user_id = message.chat.id
    user = db["users"].setdefault(user_id, {"money": 10000})

    bot.send_message(user_id, f"💰 Баланс: {user.get('money', 0)}")

@bot.message_handler(commands=['resetall'])
def reset_all(message):
    for uid in db["users"]:
        db["users"][uid]["money"] = 10000

    save_db()
    bot.send_message(message.chat.id, "Баланс всем сброшен")

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    bot.send_message(message.chat.id, "Перезапуск...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# -------------------- ТЕКСТ --------------------
@bot.message_handler(content_types=['text'])
def text(message):
    user_id = message.chat.id
    user = db["users"].setdefault(user_id, {})

    if user.get("awaiting") == "name":
        user["name"] = message.text
        user["awaiting"] = None
        user["money"] = 10000
        save_db()
        start(message)
        return

    if message.text == "Игровой автомат":
        slot_game(message)
    elif message.text == "Игральный кубик":
        dice_game(message)
    else:
        msg = bot.send_message(user_id, "Думаю...")
        answer = chat(user_id, message.text)
        send_long_message(user_id, answer)
        bot.delete_message(user_id, msg.message_id)

    save_db()

# -------------------- КУБИК --------------------
def dice_game(message):
    keyboard = telebot.types.InlineKeyboardMarkup()

    buttons = [
        telebot.types.InlineKeyboardButton(str(i), callback_data=f"dice_{i}")
        for i in range(1, 7)
    ]

    keyboard.add(*buttons)
    bot.send_message(message.chat.id, "Выбери число", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dice_"))
def dice_callback(call):
    user_id = call.message.chat.id
    user = db["users"].setdefault(user_id, {"money": 10000})

    bet = 1000
    choice = int(call.data.split("_")[1])

    if user["money"] < bet:
        bot.answer_callback_query(call.id, "Нет денег")
        return

    value = bot.send_dice(user_id, emoji="🎲").dice.value

    if value == choice:
        user["money"] += 5000
        bot.send_message(user_id, f"Угадал! +5000\nБаланс: {user['money']}")
    else:
        user["money"] -= bet
        bot.send_message(user_id, f"Не угадал ({value}) -1000\nБаланс: {user['money']}")

    save_db()
    bot.answer_callback_query(call.id)

# -------------------- СЛОТ --------------------
def slot_game(message):
    user_id = message.chat.id
    user = db["users"].setdefault(user_id, {"money": 10000})

    if user["money"] <= 0:
        bot.send_message(user_id, "Нет денег")
        return

    value = bot.send_dice(user_id, emoji="🎰").dice.value

    if value in (1, 22, 43):
        user["money"] += 1000
        bot.send_message(user_id, f"+1000 Баланс: {user['money']}")
    elif value in (16, 32, 48):
        user["money"] += 3000
        bot.send_message(user_id, f"+3000 Баланс: {user['money']}")
    elif value == 64:
        user["money"] += 10000
        bot.send_message(user_id, f"JACKPOT +10000 Баланс: {user['money']}")
    else:
        user["money"] -= 2000
        bot.send_message(user_id, f"-2000 Баланс: {user['money']}")

    save_db()

# -------------------- ЗАПУСК --------------------
bot.infinity_polling()