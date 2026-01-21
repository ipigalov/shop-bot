import pytz
import os
import telebot
from telebot import types
import requests
import json
import random
from datetime import datetime
from threading import Thread
import time
from flask import Flask


# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8401742790:AAECk0oEsrI4TgLsRGmKAFmxt2fZbYarINI'
GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxJENHWAYrSPN4129lK4IRuUbaeFwO6sFNEHlpLliWgkDGp2kySFCadi8ipqIviwN_W3w/exec'
BOT_USERNAME = '@SD_OrderShopBot'
# Вставьте сюда полученный ID (обязательно с минусом, если он есть)
GROUP_CHAT_ID = -1003663977691 

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {} 


# ==========================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ==========================================

def get_products_from_google():
    try:
        response = requests.get(GOOGLE_SCRIPT_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # --- ОТЛАДКА ---
            print("📦 ДАННЫЕ ОТ ГУГЛА:", data) 
            # Вы увидите в консоли: [{'name': 'Пицца', 'price': 600, 'stock': 5}, ...]
            # Если 'stock' нет — значит вы не обновили скрипт (Шаг 2).
            # ----------------
            return data
        return []
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

def find_product_info(short_name):
    all_products = get_products_from_google()
    for p in all_products:
        if p['name'].startswith(short_name):
            return p # Возвращаем весь объект, включая 'stock'
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
        # Рисуем кнопку повтора, если список пуст
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Попробовать снова", callback_data="retry_catalog"))
        bot.send_message(chat_id, "⚠️ Не удалось загрузить прайс. Попробуйте обновить:", reply_markup=markup)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for item in products_list:
        name = item['name']
        price = item['price']
        stock = item.get('stock', 0) # Получаем остаток (0 если нет данных)
        
        short_name = name[:20]
        
        # --- ФОРМИРУЕМ ТЕКСТ КНОПКИ ---
        if stock > 0:
            btn_text = f"{name} — {price}₽ (остаток {stock} шт.)"
            # Передаем короткое имя в callback
            markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"add|{short_name}"))
        else:
            # Если товара 0, можно либо не показывать кнопку, либо сделать неактивной
            # Мы просто не добавляем кнопку, чтобы не путать
            pass
    
    # КНОПКИ КОРЗИНЫ
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
# 3. ОБРАБОТКА НАЖАТИЙ (ИСПРАВЛЕННАЯ)
# ==========================================

@bot.callback_query_handler(func=lambda call: True)
def handle_catalog_clicks(call):
    chat_id = call.message.chat.id
    
    # --- КНОПКИ ПОВТОРА (ЕСЛИ БЫЛА ОШИБКА) ---
    if call.data == "retry_catalog":
        bot.answer_callback_query(call.id, "Загружаю...")
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        show_product_catalog(chat_id, "👇 Каталог товаров:")
        return

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

    # --- ПРОВЕРКА СЕССИИ ---
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Сессия истекла")
        start_private(call.message)
        return

    # --- ЛОГИКА МЕНЮ ---
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

    # --- ВОТ ТУТ БЫЛА ОШИБКА ---
    elif call.data.startswith("add|"):
        short_name = call.data.split("|")[1]
        
        full_product = find_product_info(short_name)
        
        if full_product:
            stock = full_product.get('stock', 0)
            
            user_data[chat_id]['current_product'] = full_product['name']
            user_data[chat_id]['current_price'] = full_product['price']
            user_data[chat_id]['max_qty'] = stock 
            user_data[chat_id]['mode'] = 'add'
            
            msg = bot.send_message(
                chat_id, 
                f"Товар: **{full_product['name']}**\n"
                f"Цена: {full_product['price']}₽\n"
                f"Доступно: {stock} шт.\n\n"
                f"Введите количество:", 
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, save_quantity)
        else:
            bot.answer_callback_query(call.id, "Ошибка товара")

    elif call.data.startswith("mod|"):
        short_name = call.data.split("|")[1]
        full_name = short_name
        # Ищем полное имя в корзине
        for item in user_data[chat_id]['cart']:
            if item.startswith(short_name):
                full_name = item
                break
        
        user_data[chat_id]['current_product'] = full_name
        user_data[chat_id]['current_price'] = user_data[chat_id]['cart'][full_name]['price']
        # При редактировании лимит считается иначе, но для простоты берем тот же max_qty если он сохранился
        # Или можно не проверять лимит жестко при уменьшении
        user_data[chat_id]['mode'] = 'edit'
        # Пытаемся восстановить max_qty из справочника снова
        p_info = find_product_info(short_name)
        if p_info:
             user_data[chat_id]['max_qty'] = p_info.get('stock', 999)

        msg = bot.send_message(chat_id, f"Введите новое количество для **{full_name}** (0 - удалить):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_quantity)

# ==========================================
# 4. ЛОГИКА КОРЗИНЫ
# ==========================================

def save_quantity(message):
            user_id = message.chat.id
    
    # --- ЗАЩИТА ОТ СТИКЕРОВ, ГИФОК И ФОТО ---
    # Если сообщение не текстовое (content_type != 'text') 
    # ИЛИ если по какой-то причине текста нет (is None)
    if message.content_type != 'text' or message.text is None:
        msg = bot.send_message(
            user_id, 
            "⛔️ **Я не понимаю этот формат.**\n"
            "Стикеры, гифки и картинки я читать не умею.\n\n"
            "Пожалуйста, просто напишите **цифру** на клавиатуре:",
            parse_mode="Markdown"
        )
        # ВАЖНО: Снова активируем ожидание ввода!
        bot.register_next_step_handler(msg, save_quantity)
        return
    # ----------------------------------------

    # Теперь мы уверены, что это текст. Проверяем команду старт.
    if message.text == '/start': 
        start_private(message)
        return
    
    # Проверяем, что текст состоит только из цифр
    if not message.text.isdigit():
        msg = bot.send_message(
            user_id, 
            "⚠️ **Это не число.**\n"
            "Пожалуйста, введите количество цифрами (например: 1, 2, 5):"
        )
        bot.register_next_step_handler(msg, save_quantity)
        return

    # --- ЕСЛИ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (ЭТО ЧИСЛО) ---

    qty = int(text)
    
    # Достаем данные
    product = user_data[user_id]['current_product']
    price = user_data[user_id]['current_price']
    max_qty = user_data[user_id].get('max_qty', 999) # Лимит
    mode = user_data[user_id].get('mode', 'add')
    cart = user_data[user_id]['cart']
    
    # --- ЛОГИКА ПРОВЕРКИ ---
    
    # Смотрим, сколько этого товара УЖЕ лежит в корзине
    already_in_cart = 0
    if product in cart and mode == 'add':
        already_in_cart = cart[product]['qty']
        
    # Сколько всего хочет пользователь
    total_wanted = qty if mode == 'edit' else (qty + already_in_cart)
    
    # Сколько еще можно добавить
    available_to_add = max_qty - already_in_cart
    if available_to_add < 0: available_to_add = 0
    
    # Если превышен лимит
    if total_wanted > max_qty:
        error_msg = (
            f"❌ **К сожалению, такого количества товара нет в наличии.**\n"
            f"Скорректируйте заказ.\n\n"
            f"Всего на складе: {max_qty} шт.\n"
            f"У вас в корзине: {already_in_cart} шт.\n"
            f"👇 **Доступно к заказу не более: {available_to_add} шт.**\n\n"
            f"Введите меньшее количество:"
        )
        msg = bot.send_message(user_id, error_msg, parse_mode="Markdown")
        bot.register_next_step_handler(msg, save_quantity) # Ждем ввода снова
        return
    # -----------------------

    # Если всё ок - сохраняем
    if mode == 'edit':
        if qty == 0:
            if product in cart: del cart[product]
        else:
            # ДОБАВИЛИ 'max_qty': max_qty
            cart[product] = {'qty': qty, 'price': price, 'max_qty': max_qty}
        show_edit_menu(user_id)
    else:
        # Добавление
        if product in cart:
            cart[product]['qty'] += qty
            cart[product]['price'] = price
            # max_qty не обновляем, он тот же
        else:
            # ДОБАВИЛИ 'max_qty': max_qty
            cart[product] = {'qty': qty, 'price': price, 'max_qty': max_qty}
            
        show_product_catalog(user_id, f"✅ Добавлено: {product} ({qty} шт.)")
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
# --- ИСПРАВЛЕНИЕ ВРЕМЕНИ (МОСКВА) ---
        # Получаем часовой пояс Москвы
        msk_tz = pytz.timezone('Europe/Moscow')
        # Получаем текущее время сразу в нужном поясе
        now = datetime.now(msk_tz)
         
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
                f"📅 **Время:** {time_str}(МСК)\n"
                f"💰 **Сумма:** {total_sum}₽\n\n"
                f"Спасибо за заказ!\n"
   		f" Следите за сообщениями в TГ группе РАСПРОДАЖИ СЕВЕРНАЯ ДОЛИНА и в БИТРИКС о дате и времени выдачи, а также о возможных изменениях!"
            )
            bot.send_message(user_id, final_message, parse_mode="Markdown")

     # --- НОВОЕ: ПРОВЕРКА НА ОКОНЧАНИЕ ТОВАРА ---
            try:
                alert_text = ""
                for name, data in cart.items():
                    ordered_qty = data['qty']
                    original_stock = data.get('max_qty', 999)
                    
                    # Логика: Если купили всё, что было (или больше)
                    remaining = original_stock - ordered_qty
                    
                    if remaining <= 0:
                        alert_text += f"🔴 **ЗАКОНЧИЛСЯ ТОВАР:** {name}\n"
                    elif remaining < 3: # Можно добавить предупреждение если мало
                        alert_text += f"🟡 **Заканчивается:** {name} (Ост: {remaining})\n"
                
                # Если есть о чем предупредить - пишем в ГРУППУ
                if alert_text:
                    full_alert = (f"⚡️ **ВНИМАНИЕ СКЛАД!**\n"
                                  f"После заказа #{order_id}:\n\n"
                                  f"{alert_text}")
                    bot.send_message(GROUP_CHAT_ID, full_alert, parse_mode="Markdown")
                    
            except Exception as e:
                print(f"Ошибка отправки алерта: {e}")
            # -------------------------------------------
            
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

# ==========================================
# ОБРАБОТКА СООБЩЕНИЙ В ГРУППЕ
# ==========================================
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'])
def handle_group_logic(message):
    # 1. Если нажали "Запросить остатки" или ввели команду
    if message.text == "📊 Актуальные остатки" or message.text == "/stock":
        send_stock_report_to_group(message.chat.id)
        return

    # 2. Если пишут "Заказ" - отправляем в личку (старая логика)
    if message.text.lower().startswith('заказ') or message.text.startswith('/start'):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="➡️ Перейдите в бот", url=f"https://t.me/{BOT_USERNAME}"))
        bot.reply_to(message, "Для оформления заказа перейдите в личные сообщения:", reply_markup=markup)

    # 3. Если админ пишет /menu, показываем клавиатуру в группе
    if message.text == "/menu":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("📊 Актуальные остатки"))
        bot.send_message(message.chat.id, "Меню администратора:", reply_markup=markup)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run_http():
    # Магия здесь: берем порт от Render или используем 8080 по умолчанию
    port = int(os.environ.get("PORT", 8080))
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

keep_alive() # Запускаем сервер в фоновом потоке

# ==========================================
# СООБЩЕНИЕ ОБ ОСТАТКАХ В ГРУППЕ
# ==========================================

def send_stock_report_to_group(chat_id):
    bot.send_message(chat_id, "⏳ Загружаю данные со склада...")
    products = get_products_from_google()
    
    if not products:
        bot.send_message(chat_id, "⚠️ Ошибка получения данных.")
        return

    report_lines = []
    for p in products:
        name = p['name']
        stock = p.get('stock', 0)
        
        # Ставим значок в зависимости от количества
        icon = "🟢"
        if stock < 5: icon = "🟡"
        if stock == 0: icon = "🔴"
        
        report_lines.append(f"{icon} {name}: **{stock} шт.**")
        
    report_text = "📦 **СКЛАД НА ТЕКУЩИЙ МОМЕНТ:**\n\n" + "\n".join(report_lines)
    
    bot.send_message(chat_id, report_text, parse_mode="Markdown")
print("Бот готов к работе!")
bot.infinity_polling()