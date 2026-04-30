import os
import re
import json
import logging
import requests
from dotenv import load_dotenv
from  flask import Flask, request
import telebot
from telebot import util
import sys
BET = 1000

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
ROLES = {
    "default": "Ты - недружелюбный помощник.",
    "smart": "Ты - умный помощник.вои ответы должны быть умными и точными "
}


def chat(user_id, text):
    try:
        if str(user_id) not in history:
            history[str(user_id)] = [{"role": "system","content": ROLES["default"] }]

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
            logging.info(f"data: {data}")
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
#                       =============Команды============

@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.chat.id

        if user_id not in db["users"] or db ["users"].get(user_id).get("awaiting") == ("name"):
            db["users"][user_id] = {}
            db["users"][user_id]["awaiting"] = "name"
            save_db()
            bot.send_message(message.chat.id, "Напиши своё имя,советую писать не настоящее")

            return

        db["users"][user_id]["money"] = 20000
        save_db()
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

        slot_button = telebot.types.KeyboardButton("Игровой автомат")
        dice_button = telebot.types.KeyboardButton("Игральный кубик")

        keyboard.add(slot_button, dice_button)
        role_button = telebot.types.KeyboardButton(text="Можешь сменить роль здесь")
        bot.send_message(message.chat.id, f"Привет",{db["users"][user_id]["awaiting"]}, reply_markup=keyboard)
        keyboard.add(role_button)
    except Exception as e:
        bot.edit_message_reply_markup(message, f"Ошибка: {e}")


@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id, "Бот создан в качестве просто развлечения")

@bot.message_handler(commands=['balance'])
def balance(message):
        message.chat.id

@bot.message_handler(commands=['bet'])
def set_bet(message):
    user_id = message.chat.id
    user = db["users"].setdefault(user_id, {})

    if "money" not in user:
        user["money"] = 10000
        save_db()

    bot.send_message(user_id, f" Баланс: {user['money']}")
    args = message.text.split()

    if len(args) < 2 or not args[1].isdigit():
        bot.send_message(user_id, "Пример: /bet 1000")
        return

    bet = int(args[1])

    if bet <= 0:
        bot.send_message(user_id, "Ставка должна быть > 0")
        return

    db["users"][user_id]["bet"] = bet
    save_db()

    bot.send_message(user_id, f" Ставка установлена: {bet}")
    BET = db["users"][user_id].get("bet", 1000)



@bot.message_handler(content_types=['text'])
def text(message):
    user_id = message.chat.id

    user = db["users"][user_id]
    BET = user.get("bet", 1000)

    # удача (чуть повышает шанс)
    luck = user.get("luck", 0)

    import random
    if random.randint(1, 100) < luck:
        value = 64


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
        elif text == "Сменить роль":
            keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
            btn_default = telebot.types.InlineKeyboardButton("Помощник", callback_data="role_default")
            btn_smart = telebot.types.InlineKeyboardButton("Умный", callback_data="role_smart")
            keyboard.add(btn_default, btn_smart)
        bot.send_message(message.chat.id,
                         "Выбери новую личность для нейросети. Внимание: это очистит историю диалога", reply_markup=keyboard)
    else:
        msg = bot.send_message(message.chat.id, "Думаю над ответом")
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
    print('test')
    keyboard.add(btn1, btn2, btn3, btn4, btn5, btn6)

    bot.send_message(message.chat.id, "Угадайте число на кубике", reply_markup=keyboard)




@bot.callback_query_handler(func=lambda call: call.data.startswith("dice_"))
def KeyboardButton(call):
    user_id = call.message.chat.id

    choice = call.data.split("_")[1]  # что выбрал пользователь

    bet = db["users"][user_id].get("bet", 1000)

    if db["users"][user_id]["money"] < bet:
        bot.answer_callback_query(call.id, "Недостаточно денег")
        return

    value = bot.send_dice(user_id, emoji="🎲").dice.value

    if str(value) == choice:
        win = 5000
        db["users"][user_id]["money"] += win
        bot.send_message(user_id, f" Угадал! Выпало {value}\n+{win}\nБаланс: {db['users'][user_id]['money']}")
    else:
        db["users"][user_id]["money"] -= BET
        bot.send_message(user_id, f" Не угадал (выпало {value})\n-{BET}\nБаланс: {db['users'][user_id]['money']}")

    save_db()
    bot.answer_callback_query(call.id,"Как так то, попробуй еще раз")

def slot_game(message):
    user_id = message.chat.id
    user = db["users"].setdefault(user_id, {})

    # если вдруг нет денег
    if "money" not in user:
        user["money"] = 10000

    if user["money"] <= 0:
        bot.send_message(user_id, "У тебя нет денег")
        return

    dice = bot.send_dice(user_id, emoji="🎰")
    value = dice.dice.value if dice and dice.dice else 0

    if value in (1, 22, 43):
        win = 1000
        user["money"] += win
        bot.send_message(user_id, f" Победа +{win}\nБаланс: {user['money']}")

    elif value in (16, 32, 48):
        win = 3000
        user["money"] += win
        bot.send_message(user_id, f" Победа +{win}\nБаланс: {user['money']}")

    elif value == 64:
        win = 10000
        user["money"] += win
        bot.send_message(user_id, f" JACKPOT +{win}\nБаланс: {user['money']}")

    else:
        lose = 1000
        user["money"] -= lose
        bot.send_message(user_id, f" Проиграл -{lose}\nБаланс: {user['money']}")

        save_db()

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