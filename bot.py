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

# ================= CHECKOUT COMPLET =================

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
