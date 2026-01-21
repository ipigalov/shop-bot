
import telebot
from telebot import types
import requests
import json
import random
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8401742790:AAECk0oEsrI4TgLsRGmKAFmxt2fZbYarINI'
GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxJENHWAYrSPN4129lK4IRuUbaeFwO6sFNEHlpLliWgkDGp2kySFCadi8ipqIviwN_W3w/exec'
BOT_USERNAME = '@SD_OrderShopBot'

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {} 


# ==========================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ==========================================

def get_products_from_google():
    try:
        response = requests.get(GOOGLE_SCRIPT_URL, timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"Ошибка получения товаров: {e}")
        return []

def find_product_info(short_name):
    all_products = get_products_from_google()
    for p in all_products:
        if p['name'].startswith(short_name):
            return p
    return None

# ==========================================
# 1. СТАРТ
# ==========================================

@bot.message_handler(commands=['start'], func=lambda message: message.chat.type == 'private')
def start_private(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if message.chat.id in user_data: del user_data[message.chat.id]
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛍 Начать заказ")
    bot.send_message(message.chat.id, "👋 Добро пожаловать! Нажмите кнопку для заказа.", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🛍 Начать заказ")
def ask_fio_step(message):
    markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(message.chat.id, "Чтобы мы приняли заказ именно для Вас и не перепутали, введите, пожалуйста, Ваше **ФИО**:", reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_fio_and_show_catalog)

def save_fio_and_show_catalog(message):
    if message.text == '/start': start_private(message); return
    
    user_id = message.chat.id
    user_data[user_id] = {'fio': message.text, 'cart': {}}
    
    bot.send_message(user_id, "🔄 Загружаю перечень товаров и цены...")
    show_product_catalog(user_id, "👇 Выберите товары в корзину, последовательно нажимая на кнопки с названиями товаров ниже, и указывая количество. Количество шт в заказе должно быть кратно количестве в коробе (указано в скобках в конце названия):")

# ==========================================
# 2. КАТАЛОГ И РЕДАКТИРОВАНИЕ
# ==========================================

def show_product_catalog(chat_id, text_message):
    products_list = get_products_from_google()
    
    if not products_list:
        bot.send_message(chat_id, "⚠️ Ошибка загрузки прайс-листа.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Кнопки товаров
    for item in products_list:
        name = item['name']
        price = item['price']
        short_name = name[:20] # Обрезаем для callback_data
        
        btn_text = f"{name} — {price}₽"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"add|{short_name}"))
    
    # Сборка текста корзины ПРЯМО ЗДЕСЬ
    cart = user_data[chat_id].get('cart', {})
    total_sum = 0
    cart_lines = []
    
    if cart:
        for p_name, p_data in cart.items():
            qty = p_data['qty']
            price = p_data['price']
            line_sum = qty * price
            total_sum += line_sum
            cart_lines.append(f"▫️ {p_name}: {qty} шт. x {price} = {line_sum}₽")
        
        # Кнопки управления
        markup.add(types.InlineKeyboardButton(text=f"✅ Оформить ({total_sum}₽)", callback_data="checkout"))
        markup.add(types.InlineKeyboardButton(text="✏️ Ред. корзину", callback_data="edit_cart_menu"))
        markup.add(types.InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart"))

    cart_text_display = "\n".join(cart_lines)
    if not cart_text_display: cart_text_display = "Пусто"
    
    full_text = f"{text_message}\n\n🛒 **Ваша корзина:**\n{cart_text_display}\n\n💰 **ИТОГО: {total_sum}₽**"
    
    try:
        bot.send_message(chat_id, full_text, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, full_text, reply_markup=markup)

def show_edit_menu(chat_id):
    cart = user_data[chat_id].get('cart', {})
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for product_name, p_data in cart.items():
        qty = p_data['qty']
        short_name = product_name[:20]
        markup.add(types.InlineKeyboardButton(text=f"📝 {product_name} ({qty} шт.)", callback_data=f"mod|{short_name}"))
        
    markup.add(types.InlineKeyboardButton(text="🔙 Назад к списку товаров", callback_data="back_to_catalog"))
    bot.send_message(chat_id, "Какой товар изменить?", reply_markup=markup)

# ==========================================
# 3. ОБРАБОТКА НАЖАТИЙ (CALLBACK)
# ==========================================

@bot.callback_query_handler(func=lambda call: True)
def handle_catalog_clicks(call):
    chat_id = call.message.chat.id
    
    # Обработка кнопки ПОВТОРА (если была ошибка)
    if call.data == "retry_checkout":
        try: bot.delete_message(chat_id, call.message.message_id) 
        except: pass
        send_to_google(call.message)
        return
        
    if call.data == "cancel_on_error":
        try: bot.delete_message(chat_id, call.message.message_id) 
        except: pass
        start_private(call.message)
        return

    # Проверка сессии
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Сессия истекла")
        start_private(call.message)
        return

    if call.data == "clear_cart":
        user_data[chat_id]['cart'] = {}
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        show_product_catalog(chat_id, "Корзина очищена.")

    elif call.data == "checkout":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        show_confirm_menu(chat_id)

    elif call.data == "edit_cart_menu":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        show_edit_menu(chat_id)

    elif call.data == "back_to_catalog":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        show_product_catalog(chat_id, "Каталог:")

    elif call.data.startswith("add|"):
        short_name = call.data.split("|")[1]
        full_product = find_product_info(short_name)
        
        if full_product:
            user_data[chat_id]['current_product'] = full_product['name']
            user_data[chat_id]['current_price'] = full_product['price']
            user_data[chat_id]['mode'] = 'add'
            
            msg = bot.send_message(chat_id, f"Введите количество для **{full_product['name']}**:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, save_quantity)

    elif call.data.startswith("mod|"):
        short_name = call.data.split("|")[1]
        full_name = short_name
        for item in user_data[chat_id]['cart']:
            if item.startswith(short_name):
                full_name = item
                break
        
        user_data[chat_id]['current_product'] = full_name
        user_data[chat_id]['current_price'] = user_data[chat_id]['cart'][full_name]['price']
        user_data[chat_id]['mode'] = 'edit'
        
        msg = bot.send_message(chat_id, f"Введите новое количество для **{full_name}** (0 - удалить):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_quantity)

# ==========================================
# 4. ЛОГИКА КОРЗИНЫ
# ==========================================

def save_quantity(message):
    user_id = message.chat.id
    text = message.text
    if text == '/start': start_private(message); return
    
    if not text.isdigit():
        msg = bot.send_message(user_id, "Введите число:")
        bot.register_next_step_handler(msg, save_quantity); return

    qty = int(text)
    product = user_data[user_id]['current_product']
    price = user_data[user_id]['current_price']
    mode = user_data[user_id].get('mode', 'add')
    cart = user_data[user_id]['cart']
    
    if mode == 'edit':
        if qty == 0:
            if product in cart: del cart[product]
        else:
            cart[product] = {'qty': qty, 'price': price}
        show_edit_menu(user_id)
    else:
        if product in cart:
            cart[product]['qty'] += qty
            cart[product]['price'] = price 
        else:
            cart[product] = {'qty': qty, 'price': price}
        show_product_catalog(user_id, f"✅ Добавлено: {product}")

# ==========================================
# 5. ПОДТВЕРЖДЕНИЕ И ОТПРАВКА
# ==========================================

def show_confirm_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Подтвердить заказ")
    markup.add("✏️ Скорректировать", "❌ Отменить")
    
    cart = user_data[chat_id]['cart']
    total = 0
    # Генерируем список строк ПРЯМО ЗДЕСЬ, чтобы не было ошибок переменных
    order_display_lines = []
    
    for name, data in cart.items():
        s = data['qty'] * data['price']
        total += s
        order_display_lines.append(f"{name} x {data['qty']} = {s}₽")
        
    order_text_block = "\n".join(order_display_lines)
    
    msg = f"🧾 **Ваш заказ:**\n{order_text_block}\n\n💰 **К ОПЛАТЕ: {total}₽**"
    bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler_by_chat_id(chat_id, handle_final_decision)

def handle_final_decision(message):
    user_id = message.chat.id
    text = message.text
    if text == "✅ Подтвердить заказ": send_to_google(message)
    elif text == "✏️ Скорректировать": show_edit_menu(user_id)
    elif text == "❌ Отменить": start_private(message)
    else: bot.register_next_step_handler(message, handle_final_decision)

# --- ОТПРАВКА В ГУГЛ С ПОВТОРОМ ---

def send_to_google(message):
    user_id = message.chat.id
    
    if user_id not in user_data:
        bot.send_message(user_id, "⚠️ Данные заказа устарели. Начните заново.")
        return

    try:
        fio = user_data[user_id]['fio']
        username = message.from_user.username or "-"
        
        # Дата и ID
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M")
        full_date = f"{date_str} {time_str}"
        
        if 'order_id' not in user_data[user_id]:
            user_data[user_id]['order_id'] = str(random.randint(100000, 999999))
        order_id = user_data[user_id]['order_id']
        
        # Сборка данных для JSON
        cart = user_data[user_id]['cart']
        items_list = []
        total_sum = 0
        
        for name, data in cart.items():
            items_list.append({'name': name, 'qty': data['qty']})
            total_sum += data['qty'] * data['price']
            
        payload = {
            'date': full_date,
            'order_id': order_id,
            'fio': fio,
            'nick': f"@{username}",
            'items': items_list
        }
        
        bot.send_message(user_id, "⏳ Отправка...", reply_markup=types.ReplyKeyboardRemove())
        
        # Отправляем
        response = requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            final_message = (
                f"✅ **ЗАКАЗ ПОДТВЕРЖДЕН!**\n\n"
                f"🔢 **Номер заказа:** `#{order_id}`\n"
                f"📅 **Время:** {time_str}\n"
                f"💰 **Сумма:** {total_sum}₽\n\n"
                f"Спасибо за заказ!\n"
   		f" Следите за сообщениями в TГ группе РАСПРОДАЖИ СЕВЕРНАЯ ДОЛИНА о дате и времени выдачи, а также о возможных изменениях!"
            )
            bot.send_message(user_id, final_message, parse_mode="Markdown")
            
            del user_data[user_id]
            start_private(message)
        else:
            raise Exception(f"Google Error: {response.status_code}")

    except Exception as e:
        print(f"Ошибка: {e}")
        ask_to_retry(user_id)

def ask_to_retry(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Попробовать снова", callback_data="retry_checkout"))
    markup.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_on_error"))
    
    bot.send_message(
        chat_id, 
        f"⚠️ **Ошибка соединения.**\nНе удалось отправить заказ. Попробуйте еще раз.",
        reply_markup=markup, parse_mode="Markdown"
    )

# --- ГРУППА ---
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'])
def handle_group(message):
    if message.text.lower().startswith('заказ') or message.text.startswith('/start'):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="Перейти в бот", url=f"https://t.me/{BOT_USERNAME}"))
        bot.reply_to(message, "Для заказа перейдите в личные сообщения:", reply_markup=markup)

print("Бот готов к работе!")
bot.infinity_polling()