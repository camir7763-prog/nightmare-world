import os
import re
import json
import logging
import requests
import random
from dotenv import load_dotenv
from flask import Flask, request
import telebot
from telebot import util

# Загружаем переменные окружения в самом начале
load_dotenv(".env")

BET_DEFAULT = 1000
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.warning("BOT_TOKEN не задан в переменных окружения")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

MAX_LEN = 4096

def convert_markdown_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    return text

def send_long_message(chat_id, text, parse_mode='HTML'):
    try:
        safe_text = convert_markdown_to_html(text or "")
        for part in util.smart_split(safe_text, MAX_LEN):
            bot.send_message(chat_id, part, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Ошибка при отправке длинного сообщения: {e}")

@app.route('/')
def index():
    return "bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_str)
        if update:
            bot.process_new_updates([update])
    except Exception as e:
        app.logger.exception("Webhook error: %s", e)
    return '', 200

# --- ИСТОРИЯ ДИАЛОГОВ ---
history_file = "history.json"
history = {}

if os.path.exists(history_file):
    try:
        with open(history_file, "r", encoding='utf-8') as f:
            history = json.load(f)
    except Exception:
        history = {}

def save_history():
    try:
        with open(history_file, "w", encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения истории: {e}")

API_KEY = os.getenv('API_KEY')
if not API_KEY:
    logging.warning("sk-f2f178791b084c1191573b7fee3b4cfa")

ROLES = {
    "default": "Ты - недружелюбный помощник.",
    "smart": "Ты - умный помощник. Твои ответы должны быть умными и точными."
}

def chat(user_id, text):
    uid = str(user_id)
    try:
        if uid not in history:
            history[uid] = [{"role": "system", "content": ROLES["default"]}]

        history[uid].append({"role": "user", "content": text})
        if len(history[uid]) > 16:
            history[uid] = [history[uid][0]] + history[uid][-15:]

        url = "https://io.solutions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}" if API_KEY else ""
        }
        data = {"model": "deepseek-ai/DeepSeek-R1-0528", "messages": history[uid]}

        response = requests.post(url, headers=headers, json=data, timeout=300)
        res_data = response.json()

        if isinstance(res_data, dict) and res_data.get('choices'):
            content = res_data['choices'][0]['message']['content']
            history[uid].append({"role": "assistant", "content": content})

            if len(history[uid]) > 16:
                history[uid] = [history[uid][0]] + history[uid][-15:]

            save_history()

            if '</think>' in content:
                return content.split('</think>', 1)[1]
            return content
        else:
            logging.error(f"Ошибка API: {res_data}")
            return "Не удалось получить ответ от ИИ."
    except Exception as e:
        logging.error(f"Ошибка при запросе к ИИ: {e}")
        return f"Ошибка при запросе: {e}, повторите попытку позже"

# --- ИГРОВАЯ БАЗА ДАННЫХ ---
db = {"users": {}}
db_path = "db.json"

def save_db():
    with open(db_path, "w", encoding='utf-8') as file:
        json.dump(db, file, ensure_ascii=False, indent=4)

if os.path.exists(db_path) and os.path.getsize(db_path) != 0:
    try:
        with open(db_path, "r", encoding='utf-8') as file:
            db = json.load(file)
    except Exception:
        db = {"users": {}}
else:
    save_db()

# --- КОМАНДЫ БОТА ---

@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = str(message.chat.id)

        if user_id not in db["users"] or db["users"][user_id].get("awaiting") == "name":
            db["users"][user_id] = {"awaiting": "name"}
            save_db()
            bot.send_message(message.chat.id, "Напиши своё имя, советую писать не настоящее")
            return

        db["users"][user_id]["money"] = db["users"][user_id].get("money", 20000)
        save_db()
        
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        slot_button = telebot.types.KeyboardButton("Игровой автомат")
        dice_button = telebot.types.KeyboardButton("Игральный кубик")
        role_button = telebot.types.KeyboardButton("Сменить роль")
        keyboard.add(slot_button, dice_button)
        keyboard.add(role_button)
        
        name = db["users"][user_id].get("name", "Игрок")
        bot.send_message(message.chat.id, f"Привет, {name}!", reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Ошибка в start: {e}")

@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id, "Бот создан в качестве простого развлечения")

@bot.message_handler(commands=['balance'])
def balance(message):
    user_id = str(message.chat.id)
    money = db["users"].get(user_id, {}).get("money", 0)
    bot.send_message(message.chat.id, f"Ваш баланс: {money}")

@bot.message_handler(commands=['bet'])
def set_bet(message):
    user_id = str(message.chat.id)
    user = db["users"].setdefault(user_id, {})

    if "money" not in user:
        user["money"] = 10000
        save_db()

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.send_message(user_id, f"Баланс: {user['money']}\nПример установки ставки: /bet 1000")
        return

    bet = int(args[1])
    if bet <= 0:
        bot.send_message(user_id, "Ставка должна быть > 0")
        return

    user["bet"] = bet
    save_db()
    bot.send_message(user_id, f"Ставка установлена: {bet}")

@bot.message_handler(content_types=['text'])
def text_handler(message):
    user_id = str(message.chat.id)
    
    if user_id not in db["users"]:
        db["users"][user_id] = {"awaiting": "name"}
        save_db()

    user = db["users"][user_id]

    # Шаг 1. Проверка регистрации имени
    if user.get("awaiting") == "name":
        user["name"] = message.text
        user["awaiting"] = None
        user["money"] = 10000
        save_db()
        start(message)
        return

    # Шаг 2. Обычные команды меню
    if message.text == "Привет":
        bot.send_message(message.chat.id, "Задавай вопрос и не тупи")
        return
    elif message.text == "Как дела?":
        bot.send_message(message.chat.id, "Отлично")
        return
    elif message.text == "Игровой автомат":
        slot_game(message)
        return
    elif message.text == "Игральный кубик":
        dice_game(message)
        return
    elif message.text == "Сменить роль":
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        btn_default = telebot.types.InlineKeyboardButton("Помощник", callback_data="role_default")
        btn_smart = telebot.types.InlineKeyboardButton("Умный", callback_data="role_smart")
        keyboard.add(btn_default, btn_smart)
        bot.send_message(message.chat.id, "Выбери новую личность для нейросети. Внимание: это очистит историю диалога", reply_markup=keyboard)
        return

    # Шаг 3. Обработка ИИ
    msg = bot.send_message(message.chat.id, "Думаю над ответом...")
    try:
        answer = chat(message.chat.id, message.text)
        send_long_message(message.chat.id, answer)
    except Exception as e:
        logging.error(e)
        bot.send_message(message.chat.id, "Возникла ошибка при обработке запроса")
    finally:
        try:
            bot.delete_message(message.chat.id, msg.message_id)
        except Exception:
            pass
    save_db()

def dice_game(message):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=3)
    btn1 = telebot.types.InlineKeyboardButton("1", callback_data="dice_1")
    btn2 = telebot.types.InlineKeyboardButton("2", callback_data="dice_2")
    btn3 = telebot.types.InlineKeyboardButton("3", callback_data="dice_3")
    btn4 = telebot.types.InlineKeyboardButton("4", callback_data="dice_4")
    btn5 = telebot.types.InlineKeyboardButton("5", callback_data="dice_5")
    btn6 = telebot.types.InlineKeyboardButton("6", callback_data="dice_6")
    keyboard.add(btn1, btn2, btn3, btn4, btn5, btn6)
    bot.send_message(message.chat.id, "Угадайте число на кубике", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dice_"))
def dice_callback(call):
    user_id = str(call.message.chat.id)
    choice = call.data.split("_")[1]
    
    user = db["users"].get(user_id, {})
    bet = user.get("bet", BET_DEFAULT)

    if user.get("money", 0) < bet:
        bot.answer_callback_query(call.id, "Недостаточно денег")
        return

    dice_msg = bot.send_dice(user_id, emoji="🎲")
    value = dice_msg.dice.value

    if str(value) == choice:
        win = bet * 5  # Коэффициент x5 за угаданное число
        user["money"] += win
        bot.send_message(user_id, f"🎯 Угадал! Выпало {value}\n+{win}\nБаланс: {user['money']}")
    else:
        user["money"] -= bet
        bot.send_message(user_id, f"❌ Не угадал (выпало {value})\n-{bet}\nБаланс: {user['money']}")

    save_db()
    bot.answer_callback_query(call.id, "Результат засчитан!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("role_"))

def role_callback(call):
    user_id = str(call.message.chat.id)
    role_type = call.data.split("_")[1]
    
    if role_type in ROLES:
        history[user_id] = [{"role": "system", "content": ROLES[role_type]}]
        save_history()
        bot.send_message(user_id, f"Роль успешно изменена!")
        bot.answer_callback_query(call.id)
        
        def slot_game(message):user_id = str(message.chat.id)
            user = db["users"].setdefault(user_id, {})
        if "money" not in user:
            user["money"] = 10000
            
            bet = user.get("bet", BET_DEFAULT)
        if user["money"] < bet:
            bot.send_message(user_id, "У тебя недостаточно денег для ставки!")
            return
            dice = bot.send_dice(user_id, emoji="🎰")
            value = dice.dice.value if dice and dice.dice else 0
# Выигрышные комбинации для автомата (777, три одинаковых и т.д.)
            if value in (1, 22, 43):
                win = bet * 2
                user["money"] += win
                bot.send_message(user_id, f"Победа! +{win}\nБаланс: {user['money']}")
            elif value in (16, 32, 48):
                win = bet * 5user["money"] += win
                bot.send_message(user_id, f"Большая победа! +{win}\nБаланс: {user['money']}")
        elif value == 64:win = bet * 20user["money"] += winb
        ot.send_message(user_id, f"🎰 JACKPOT! +{win}\nБаланс: {user['money']}")
    else:user["money"] -= bet
        bot.send_message(user_id, f"Проиграл -{bet}\nБаланс: {user['money']}")save_db()
        if name == "main":
            server_url = os.getenv("RENDER_EXTERNAL_URL")
            if server_url and TOKEN:
                webhook_url = f"{server_url.rstrip('/')}/{TOKEN}"
                try:
                    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                                     params={"url": webhook_url}, timeout=10)logging.info("Webhook установлен: %s", r.text)
                    port = int(os.environ.get("PORT", 10000))
                    logging.info("Starting server on port %s", port)
                    app.run(host='0.0.0.0', port=port)except Exception:
                        logging.exception("Ошибка при установке Webhook. Переключение на polling.")
                        bot.infinity_polling()
                else:
                    bot.infinity_polling()
