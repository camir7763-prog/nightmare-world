import os
import re
import json
import logging
import requests
from dotenv import load_dotenv
from  flask import Flask, request
import telebot
from telebot import util

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.warning("BOT_TOKEN не задан в переменных окружения")
    load_dotenv(".env")
    TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode=None)
app = Flask(__name__)

MAX_LEN = 4096

def convert_markdown_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    text = re.sub(r'`([^`]`)', r'<code>\1</code>', text)
    text = re.sub(r'\[(.*?)\](\(.*?)\)', r'<a href="\2">>\1</b>', text)
    return text

def send_long_message(chat_id, text, parse_mode='HTML'):
    try:
        safe_text = convert_markdown_to_html(text or "")
        for part in util.smart_split(safe_text, MAX_LEN):
            bot.send_message(chat_id, part, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Ошибка: {e}")


@app.route('/')
def index():
    return "bot is running!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str =request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_str)
        if update:
            bot.process_new_updates([update])

    except Exception as e:
        app.logger.exception("Webhook error: %s", e)
    return '', 200


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
        logging.error(("Ошибка сохранения истории:%s", e))


API_KEY = os.getenv('API_KEY')
if not API_KEY:
    logging.warning("API_KEY не задан: чат_модель будет недоступна")
    load_dotenv(".env")
    API_KEY = os.getenv("API_KEY")

def chat(user_id, text):
    try:
        if str(user_id) not in history:
            history[str(user_id)] = [{"role": "system","content": "Ты - ИИ фембой помошник"}]
        history[str(user_id)].append({"role": "user", "content":text})
        if len(history[str(user_id)]) > 16:
            history[str(user_id)] = [history[str(user_id)][0]] + history[str(user_id)][-15:]

        url = "https://api.intelligence.io.solutions/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization":f"Bearer {API_KEY}" if API_KEY else ""}
        data = {"model": "deepseek-ai/DeepSeek-R1-0528","messages": history[str(user_id)]}

        response = requests.post(url, headers=headers, json=data, timeout=300)
        data = response.json()

        if isinstance(data, dict) and data.get('choices'):
            content = data['choices'][0]['message']['content']
            history[str(user_id)].append({"role": "assistant", "content": content})

            if len(history[str(user_id)]) > 16:
                history[str(user_id)] = [history[str(user_id)][0]] + history[str(user_id)][-15:]

            save_history()

            if '</think>' in content:
                return content.split('</think>', 1)[1]
            return content
        else:
            logging.error(f"Ошибка API: ")
    except Exception as e:
        logging.error(f"Ошибка при запросе")
        send_long_message(user_id, f"ошибка при запросе: {e}, повторите попытку позже")



db = {"users": {}}
db_path = "db.json"


def save_db():
    with open("db.json", "w", encoding='utf-8') as file:
        json.dump(db, file, ensure_ascii=False, indent=4)
        
if os.path.exists(db_path) and os.path.getsize(db_path) != 0:
    with open(db_path, "r", encoding='utf-8') as file:
        db = json.load(file)
else:
    with open("db.json", "w", encoding='utf-8') as file:
        json.dump(db, file, ensure_ascii=False, indent=4)


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id

    if user_id not in db["users"] or db ["users"].get(user_id).get("awaiting") == ("name"):
        db["users"][user_id] = {}
        db["users"][user_id]["awaiting"] = "name"
        save_db()
        bot.send_message(message.chat.id, "Приветик")

        return

    db["users"][user_id]["money"] = 20000
    save_db()
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

    slot_button = telebot.types.KeyboardButton("Игровой автомат")
    dice_button = telebot.types.KeyboardButton("Игральный кубик")

    keyboard.add(slot_button, dice_button)

    bot.send_message(message.chat.id, f"Привет",{db["users"][user_id]["awaiting"]}, reply_markup=keyboard)

@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id, "Информация о боте")

@bot.message_handler(content_types=['text'])
def text(message):
    user_id = message.chat.id

    if db["users"].get(user_id).get("awaiting") == "name":
        db["users"][user_id]["name"] = message.text
        db["users"][user_id]["awaiting"] = None
        db["users"] [user_id]["money"] = 10000
        save_db()
        start(message)
        return


    if message.text == "Привет":
        bot.send_message(message.chat.id, "Задавай вопрос и не тупи")
    elif message.text == "Как дела?":
        bot.send_message(message.chat.id, "Отлично")
    elif message.text == "Игровой автомат":
        slot_game(message)
    elif message.text == "Игральный кубик":
        dice_game(message)
    else:
        msg = bot.send_message(message.chat.id, "")
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

    btn1 = telebot.types.KeyboardButton("1", callback_data="1")
    btn2 = telebot.types.KeyboardButton("2", callback_data="2")
    btn3 = telebot.types.KeyboardButton("3", callback_data="3")
    btn4 = telebot.types.KeyboardButton("4", callback_data="4")
    btn5 = telebot.types.KeyboardButton("5", callback_data="5")
    btn6 = telebot.types.KeyboardButton("6", callback_data="6")

    keyboard.add(btn1, btn2, btn3, btn4, btn5, btn6)

    bot.send_message(message.chat.id, "Угадайте число на кубике", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data in ('1', '2', '3', '4', '5', '6'))
def diceButtonClicked(call):
    value = bot.send_dice(call.message.chat.id, emoji="🎲").dice_game
    if str(value) == call.data:
        if str(value) == call.data:
            win = 5000  # сумма выигрыша
            db["users"][call.message.chat.id]["money"] += win

            bot.send_message(call.message.chat.id,
                             text=f"Ты выиграл {win}!\nБаланс: {db['users'][call.message.chat.id]['money']}")
        bot.send_message(call.message.chat.id, "Ты выиграл")
    else:
        bot.send_message(call.message.chat.id, "Попробуй еще раз")

def slot_game(message):
    value = bot.send_dice(message.chat.id, emoji="🎰").dice.value

    if value in (1, 22, 43):                                # 3 одинаковых значения
        db["users"][message.chat.id]["money"] += 1000
        bot.send_message(message.chat.id, "Победа сумма выиграша составила 1000. "
                                          f"Текуший баланс: {db['users'][message.chat.id]['money']}")
    elif value in (16, 32, 48):                             # Первые два значения - 7
        db["users"][message.chat.id]["money"] += 3500
        bot.send_message(message.chat.id, "Победа сумма выиграша составила 3500"
                                          f"Текуший баланс: {db['users'][message.chat.id]['money']}")

    elif value == 64:                                       # Три 7
        bot.send_message(message.chat.id, "Jackpot")
        db["users"][message.chat.id]["money"] += 30000
        bot.send_message(message.chat.id, "Победа сумма выиграша составила 30000"
                                          f"Текуший баланс: {db['users'][message.chat.id]['money']}")
    else:
        bot.send_message(message.chat.id, "Ты проиграл лох")


if __name__ == "__main__":
    server_url = os.getenv("RENDER_EXTERNAL_URL")
    if server_url and TOKEN:
        webhook_url = f"{server_url.rstrip('/')}/{TOKEN}"
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                             params={"url": webhook_url}, timeout=10)
            logging.info("Webhook установлен: %s", r.text)
            port = int(os.environ.get("PORT", 10000))
            logging.info("Starting server on port %s", port)
            app.run(host='0.0.0.0', port=port)
        except Exception:
            logging.exception("Ошибка при установке Webhook")
            bot.infinity_polling()
    else:
        bot.infinity_polling()











