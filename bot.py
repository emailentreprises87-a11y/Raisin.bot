import logging
import sqlite3
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ================= CONFIG =================

load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ================= DATABASE =================

conn = sqlite3.connect("shop.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price REAL,
    stock INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cart (
    user_id INTEGER,
    product_id INTEGER,
    quantity INTEGER
)
""")

# Table annonces
cursor.execute("""
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ================= PRODUITS PAR DÉFAUT =================

cursor.execute("SELECT COUNT(*) FROM products")
if cursor.fetchone()[0] == 0:
    produits = [
        ("ALOE GRAPE🍇🧊", 10, 3),
        ("Strawberry Watermelon🍓🍉", 10, 4),
        ("Kiwi passion fruit guava🥝🧊", 10, 2),
        ("Strawberry Banana🍓🍌", 10, 3)
    ]
    cursor.executemany(
        "INSERT INTO products (name, price, stock) VALUES (?, ?, ?)",
        produits
    )
    conn.commit()

# ================= STATES =================

class OrderState(StatesGroup):
    waiting_snapchat = State()
    waiting_city = State()
    waiting_place = State()

class RefuseState(StatesGroup):
    waiting_reason = State()

class SupportState(StatesGroup):
    waiting_message = State()

class AdminReplyState(StatesGroup):
    waiting_reply = State()

class AnnouncementState(StatesGroup):
    waiting_text = State()

# ================= DEBUG TEMPORAIRE =================

@dp.message_handler(commands=['whoami'], state="*")
async def whoami(message: types.Message):
    await message.answer(
        f"Ton ID : `{message.from_user.id}`\n"
        f"ADMIN_ID chargé : `{ADMIN_ID}`\n"
        f"Égaux : `{message.from_user.id == ADMIN_ID}`",
        parse_mode="Markdown"
    )

# ================= START =================

@dp.message_handler(commands=['start'], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🛍 Voir produits", callback_data="catalog"))
    keyboard.add(InlineKeyboardButton("🛒 Voir panier", callback_data="view_cart"))
    keyboard.add(InlineKeyboardButton("📢 Annonces", callback_data="view_announcements"))
    keyboard.add(InlineKeyboardButton("🎧 Support", callback_data="open_support"))

    await message.answer("Bienvenue 👋", reply_markup=keyboard)

# ================= ANNONCES — UTILISATEUR =================

@dp.callback_query_handler(lambda c: c.data == "view_announcements", state="*")
async def view_announcements(callback: types.CallbackQuery):
    await callback.answer()

    cursor.execute("SELECT id, message, created_at FROM announcements ORDER BY created_at DESC")
    annonces = cursor.fetchall()

    if not annonces:
        await callback.message.answer("📭 Aucune annonce pour le moment.")
        return

    for ann in annonces:
        ann_id, texte, date = ann

        # Si admin → bouton supprimer
        if callback.from_user.id == ADMIN_ID:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🗑 Supprimer", callback_data=f"del_ann_{ann_id}"))
            await callback.message.answer(f"📢 {texte}\n\n🕐 {date}", reply_markup=kb)
        else:
            await callback.message.answer(f"📢 {texte}\n\n🕐 {date}")

# ================= ANNONCES — ADMIN =================

# /annonce — ouvre le menu admin annonces
@dp.message_handler(commands=['annonce'], state="*")
async def announce_menu(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Accès refusé.")
        return
    await state.finish()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Nouvelle annonce", callback_data="new_announcement"))
    kb.add(InlineKeyboardButton("📋 Gérer les annonces", callback_data="manage_announcements"))

    await message.answer("📢 Gestion des annonces :", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "new_announcement", state="*")
async def new_announcement(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Accès refusé.", show_alert=True)
        return
    await callback.answer()
    await state.finish()
    await callback.message.answer("✏️ Écris ton annonce :")
    await AnnouncementState.waiting_text.set()

@dp.message_handler(state=AnnouncementState.waiting_text)
async def save_announcement(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("INSERT INTO announcements (message) VALUES (?)", (message.text,))
    conn.commit()

    await message.answer("✅ Annonce publiée !")
    await state.finish()

# Gérer (lister + supprimer) les annonces — admin seulement
@dp.callback_query_handler(lambda c: c.data == "manage_announcements", state="*")
async def manage_announcements(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()

    cursor.execute("SELECT id, message, created_at FROM announcements ORDER BY created_at DESC")
    annonces = cursor.fetchall()

    if not annonces:
        await callback.message.answer("📭 Aucune annonce.")
        return

    for ann in annonces:
        ann_id, texte, date = ann
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🗑 Supprimer", callback_data=f"del_ann_{ann_id}"))
        await callback.message.answer(f"📢 {texte}\n\n🕐 {date}", reply_markup=kb)

# Supprimer une annonce — admin seulement
@dp.callback_query_handler(lambda c: c.data.startswith("del_ann_"))
async def delete_announcement(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Accès refusé.", show_alert=True)
        return

    await callback.answer()
    ann_id = int(callback.data.split("_")[2])
    cursor.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    conn.commit()

    await callback.message.edit_text("🗑 Annonce supprimée.")

# ================= SUPPORT =================

@dp.message_handler(commands=['support'], state="*")
async def support_command(message: types.Message, state: FSMContext):
    await state.finish()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🐞 Bug", callback_data="support_bug"))
    kb.add(InlineKeyboardButton("❓ Refus incompris", callback_data="support_refuse"))
    kb.add(InlineKeyboardButton("💡 Amélioration", callback_data="support_suggest"))
    kb.add(InlineKeyboardButton("📝 Autre", callback_data="support_other"))
    await message.answer("🎧 Choisis une catégorie :", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "open_support")
async def support_menu(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🐞 Bug", callback_data="support_bug"))
    kb.add(InlineKeyboardButton("❓ Refus incompris", callback_data="support_refuse"))
    kb.add(InlineKeyboardButton("💡 Amélioration", callback_data="support_suggest"))
    kb.add(InlineKeyboardButton("📝 Autre", callback_data="support_other"))
    await callback.message.answer("🎧 Choisis une catégorie :", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("support_"))
async def support_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(category=callback.data)
    await callback.message.answer("✏️ Écris ton message :")
    await SupportState.waiting_message.set()

@dp.message_handler(state=SupportState.waiting_message)
async def receive_support(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✉️ Répondre", callback_data=f"reply_{user_id}"))

    await bot.send_message(
        ADMIN_ID,
        f"📩 Nouveau ticket\n\n"
        f"Utilisateur: {message.from_user.full_name}\n"
        f"ID: {user_id}\n"
        f"Catégorie: {data['category']}\n\n"
        f"{message.text}",
        reply_markup=kb
    )

    await message.answer("✅ Support contacté.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("reply_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()
    user_id = int(callback.data.split("_")[1])
    await state.update_data(reply_user=user_id)
    await callback.message.answer("✏️ Ta réponse :")
    await AdminReplyState.waiting_reply.set()

@dp.message_handler(state=AdminReplyState.waiting_reply)
async def admin_send_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await bot.send_message(data["reply_user"], f"📩 Réponse support :\n\n{message.text}")
    await message.answer("✅ Envoyé.")
    await state.finish()

# ================= CATALOG =================

@dp.callback_query_handler(lambda c: c.data == "catalog")
async def show_catalog(callback: types.CallbackQuery):
    await callback.answer()
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    for product in products:
        if product[3] > 0:
            keyboard = InlineKeyboardMarkup(row_width=5)
            max_qty = min(product[3], 5)
            buttons = [
                InlineKeyboardButton(str(i), callback_data=f"buy_{product[0]}_{i}")
                for i in range(1, max_qty + 1)
            ]
            keyboard.add(*buttons)
            await callback.message.answer(
                f"{product[1]} - {product[2]}€ (Stock {product[3]})",
                reply_markup=keyboard
            )

# ================= PANIER =================

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def add_to_cart(callback: types.CallbackQuery):
    await callback.answer()
    _, product_id, quantity = callback.data.split("_")
    product_id = int(product_id)
    quantity = int(quantity)
    user_id = callback.from_user.id

    cursor.execute("SELECT quantity FROM cart WHERE user_id=? AND product_id=?",
                   (user_id, product_id))
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            "UPDATE cart SET quantity = quantity + ? WHERE user_id=? AND product_id=?",
            (quantity, user_id, product_id)
        )
    else:
        cursor.execute(
            "INSERT INTO cart VALUES (?, ?, ?)",
            (user_id, product_id, quantity)
        )

    conn.commit()
    await callback.message.answer("✅ Ajouté au panier !")

@dp.callback_query_handler(lambda c: c.data == "view_cart")
async def view_cart(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    cursor.execute("""
    SELECT products.name, products.price, cart.quantity
    FROM cart
    JOIN products ON cart.product_id = products.id
    WHERE cart.user_id=?
    """, (user_id,))
    items = cursor.fetchall()

    if not items:
        await callback.message.answer("🛒 Panier vide.")
        return

    text = "🛒 Votre panier :\n\n"
    total = 0

    for name, price, quantity in items:
        subtotal = price * quantity
        total += subtotal
        text += f"{name} x{quantity} = {subtotal}€\n"

    text += f"\n💰 Total : {total}€"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Commander", callback_data="checkout"))
    keyboard.add(InlineKeyboardButton("❌ Vider panier", callback_data="clear_cart"))

    await callback.message.answer(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    await callback.answer()
    cursor.execute("DELETE FROM cart WHERE user_id=?", (callback.from_user.id,))
    conn.commit()
    await callback.message.answer("🗑 Panier vidé.")

# ================= CHECKOUT =================

@dp.callback_query_handler(lambda c: c.data == "checkout", state="*")
async def checkout(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback.answer()
    await callback.message.answer("Indique ton Snapchat :")
    await OrderState.waiting_snapchat.set()

@dp.message_handler(state=OrderState.waiting_snapchat)
async def get_snap(message: types.Message, state: FSMContext):
    await state.update_data(snap=message.text)
    await message.answer("Indique ta ville :")
    await OrderState.waiting_city.set()

@dp.message_handler(state=OrderState.waiting_city)
async def get_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Indique le lieu exact :")
    await OrderState.waiting_place.set()

@dp.message_handler(state=OrderState.waiting_place)
async def final_order(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id

    cursor.execute("""
    SELECT products.id, products.name, products.price, cart.quantity
    FROM cart
    JOIN products ON cart.product_id = products.id
    WHERE cart.user_id=?
    """, (user_id,))
    items = cursor.fetchall()

    if not items:
        await message.answer("❌ Panier vide.")
        await state.finish()
        return

    recap = ""
    total = 0

    for pid, name, price, qty in items:
        subtotal = price * qty
        total += subtotal
        recap += f"{name} x{qty} = {subtotal}€\n"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Accepter", callback_data=f"accept_{user_id}"),
        InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_{user_id}")
    )
    keyboard.add(
        InlineKeyboardButton("📦 Livré", callback_data=f"delivered_{user_id}")
    )

    await bot.send_message(
        ADMIN_ID,
        f"📢 Nouvelle commande\n\n{recap}\n💰 Total : {total}€\n\n"
        f"Snap : {data['snap']}\nVille : {data['city']}\nLieu : {message.text}",
        reply_markup=keyboard
    )

    await message.answer("✅ Votre commande a été envoyée à l'admin.")
    await state.finish()

# ================= ADMIN ACTIONS =================

@dp.callback_query_handler(lambda c: c.data.startswith("accept_"))
async def accept_order(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer("Commande acceptée")
    user_id = int(callback.data.split("_")[1])
    await bot.send_message(user_id, "✅ Votre commande a été ACCEPTÉE.")

@dp.callback_query_handler(lambda c: c.data.startswith("refuse_"))
async def refuse_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()
    user_id = int(callback.data.split("_")[1])
    await state.update_data(refuse_user=user_id)
    await callback.message.answer("✏️ Raison du refus :")
    await RefuseState.waiting_reason.set()

@dp.message_handler(state=RefuseState.waiting_reason)
async def refuse_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data["refuse_user"]

    await bot.send_message(
        user_id,
        f"❌ Votre commande a été refusée.\n\nRaison : {message.text}\n\n"
        f"Si vous ne comprenez pas utilisez /support"
    )

    await message.answer("Refus envoyé ✅")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("delivered_"))
async def delivered(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.answer("Commande livrée")
    user_id = int(callback.data.split("_")[1])

    cursor.execute("SELECT product_id, quantity FROM cart WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    for pid, qty in items:
        cursor.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, pid))

    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()

    await bot.send_message(user_id, "📦 Merci ! Votre commande a bien été livrée.")
    await callback.message.delete()

# ================= RUN =================

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
