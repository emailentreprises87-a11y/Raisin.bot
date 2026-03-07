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
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

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

class ReplyAnnouncementState(StatesGroup):
    waiting_reply = State()

# ================= START =================

@dp.message_handler(commands=['start'], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (message.from_user.id,)
    )
    conn.commit()

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🛍 Voir produits", callback_data="catalog"))
    keyboard.add(InlineKeyboardButton("🛒 Voir panier", callback_data="view_cart"))
    keyboard.add(InlineKeyboardButton("🎧 Support", callback_data="open_support"))

    await message.answer("Bienvenue 👋", reply_markup=keyboard)

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

# ================= ANNONCES =================

@dp.message_handler(commands=['annonce'])
async def annonce_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("✏️ Écris ton annonce :")
    await AnnouncementState.waiting_text.set()

@dp.message_handler(state=AnnouncementState.waiting_text)
async def send_announcement(message: types.Message, state: FSMContext):

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💬 Répondre", callback_data="reply_annonce"))

        try:
            await bot.send_message(
                user[0],
                f"📢 ANNONCE ADMIN\n\n{message.text}",
                reply_markup=keyboard
            )
        except:
            pass

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🗑 Supprimer annonce", callback_data="delete_annonce"))

    await message.answer("✅ Annonce envoyée.", reply_markup=kb)

    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "reply_annonce")
async def reply_annonce(callback: types.CallbackQuery, state: FSMContext):

    await callback.answer()
    await callback.message.answer("✏️ Écris ta réponse à l'annonce :")
    await ReplyAnnouncementState.waiting_reply.set()

@dp.message_handler(state=ReplyAnnouncementState.waiting_reply)
async def send_reply_to_admin(message: types.Message, state: FSMContext):

    user_id = message.from_user.id

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✉️ Répondre", callback_data=f"reply_{user_id}"))

    await bot.send_message(
        ADMIN_ID,
        f"💬 Réponse à ton annonce\n\n"
        f"Utilisateur : {message.from_user.full_name}\n"
        f"ID : {user_id}\n\n"
        f"{message.text}",
        reply_markup=kb
    )

    await message.answer("✅ Réponse envoyée à l'admin.")

    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "delete_annonce")
async def delete_annonce(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.delete()

# ================= RUN =================
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

    cursor.execute(
        "SELECT quantity FROM cart WHERE user_id=? AND product_id=?",
        (user_id, product_id)
    )

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

    cursor.execute(
        "DELETE FROM cart WHERE user_id=?",
        (callback.from_user.id,)
    )

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

class BuyAnnonceState(StatesGroup):
    waiting_text = State()


@dp.message_handler(commands=['annonce_buy'])
async def annonce_buy(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("✏️ Texte de l'annonce produit :")
    await BuyAnnonceState.waiting_text.set()


@dp.message_handler(state=BuyAnnonceState.waiting_text)
async def annonce_buy_send(message: types.Message, state: FSMContext):

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🛍 Voir produits", callback_data="catalog")
    )

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await bot.send_message(
                user[0],
                f"🔥 PRODUIT\n\n{message.text}",
                reply_markup=keyboard
            )
        except:
            pass

    await message.answer("✅ Annonce produit envoyée.")

    await state.finish()

class LinkAnnonceState(StatesGroup):
    waiting_text = State()
    waiting_url = State()


@dp.message_handler(commands=['annonce_lien'])
async def annonce_lien_start(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("✏️ Texte de l'annonce :")
    await LinkAnnonceState.waiting_text.set()


@dp.message_handler(state=LinkAnnonceState.waiting_text)
async def annonce_lien_text(message: types.Message, state: FSMContext):

    await state.update_data(text=message.text)

    await message.answer("🔗 Envoie le lien :")

    await LinkAnnonceState.waiting_url.set()


@dp.message_handler(state=LinkAnnonceState.waiting_url)
async def annonce_lien_send(message: types.Message, state: FSMContext):

    data = await state.get_data()

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔗 Ouvrir", url=message.text)
    )

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await bot.send_message(
                user[0],
                f"📢 ANNONCE\n\n{data['text']}",
                reply_markup=keyboard
            )
        except:
            pass

    await message.answer("✅ Annonce avec lien envoyée.")

    await state.finish()

class PhotoAnnonceState(StatesGroup):
    waiting_photo = State()
    waiting_text = State()


@dp.message_handler(commands=['annonce_photo'])
async def annonce_photo_start(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("📸 Envoie la photo :")
    await PhotoAnnonceState.waiting_photo.set()


@dp.message_handler(content_types=['photo'], state=PhotoAnnonceState.waiting_photo)
async def annonce_photo_get(message: types.Message, state: FSMContext):

    photo = message.photo[-1].file_id

    await state.update_data(photo=photo)

    await message.answer("✏️ Texte de l'annonce :")

    await PhotoAnnonceState.waiting_text.set()


@dp.message_handler(state=PhotoAnnonceState.waiting_text)
async def annonce_photo_send(message: types.Message, state: FSMContext):

    data = await state.get_data()

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await bot.send_photo(
                user[0],
                data["photo"],
                caption=f"📢 ANNONCE\n\n{message.text}"
            )
        except:
            pass

    await message.answer("✅ Annonce photo envoyée.")

    await state.finish()

class BroadcastState(StatesGroup):
    waiting_text = State()


@dp.message_handler(commands=['broadcast'])
async def broadcast_start(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("✏️ Envoie le message à diffuser :")
    await BroadcastState.waiting_text.set()


@dp.message_handler(state=BroadcastState.waiting_text)
async def broadcast_send(message: types.Message, state: FSMContext):

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    sent = 0

    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            sent += 1
        except:
            pass

    await message.answer(f"✅ Message envoyé à {sent} utilisateurs")

    await state.finish()
@dp.message_handler(commands=['stats'])
async def stats(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    await message.answer(
        f"📊 Statistiques\n\n"
        f"👤 Utilisateurs : {total_users}"
    )

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
        f"❌ Votre commande a été refusée.\n\n"
        f"Raison : {message.text}\n\n"
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

    cursor.execute(
        "SELECT product_id, quantity FROM cart WHERE user_id=?",
        (user_id,)
    )

    items = cursor.fetchall()

    for pid, qty in items:
        cursor.execute(
            "UPDATE products SET stock = stock - ? WHERE id=?",
            (qty, pid)
        )

    cursor.execute(
        "DELETE FROM cart WHERE user_id=?",
        (user_id,)
    )

    conn.commit()

    await bot.send_message(
        user_id,
        "📦 Merci ! Votre commande a bien été livrée."
    )

    await callback.message.delete()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
