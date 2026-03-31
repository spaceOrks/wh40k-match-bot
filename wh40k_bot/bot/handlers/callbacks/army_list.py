from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import army_list_actions_keyboard, army_lists_keyboard
from wh40k_bot.bot.states import UploadArmyList
from wh40k_bot.services import ArmyListService, format_army_list_full

router = Router()


@router.callback_query(F.data == "upload_army_list")
async def upload_army_list_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на загрузку списка армии"""
    await callback.message.edit_text(
        "📤 <b>Загрузка списка армии</b>\n\n"
        "Отправьте JSON файл списка армии.\n\n"
        "<i>Как получить файл:</i>\n"
        "1. Откройте game-datacards\n"
        "2. List → Export as Datasource\n"
        "3. Отправьте полученный .json файл сюда",
        parse_mode="HTML"
    )
    await state.set_state(UploadArmyList.waiting_for_file)
    await callback.answer()


@router.callback_query(F.data.startswith("view_army_list:"))
async def view_army_list(callback: CallbackQuery, session: AsyncSession):
    """Просмотр списка армии"""
    army_list_id = int(callback.data.split(":")[1])

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)

    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return

    # Получаем статистику
    stats = await army_service.get_army_list_stats(army_list_id)

    # Формируем текст
    text = format_army_list_full(army_list)

    # Добавляем статистику
    text += "\n\n📊 <b>Статистика:</b>\n"
    if stats["total"] > 0:
        text += f"  🎮 Всего игр: {stats['total']}\n"
        text += f"  ✅ Побед: {stats['wins']}\n"
        text += f"  ❌ Поражений: {stats['losses']}\n"
        if stats["draws"] > 0:
            text += f"  ➖ Ничьих: {stats['draws']}\n"
        text += f"  📈 Винрейт: {stats['win_rate']}%"
    else:
        text += "  <i>Ещё не использовался в играх</i>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=army_list_actions_keyboard(army_list_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_army_list:"))
async def delete_army_list_confirm(callback: CallbackQuery):
    """Подтверждение удаления списка армии"""
    army_list_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "❓ <b>Удалить этот список армии?</b>\n\n"
        "⚠️ Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_army:{army_list_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"view_army_list:{army_list_id}")
            ]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_army:"))
async def delete_army_list(callback: CallbackQuery, session: AsyncSession):
    """Удаление списка армии"""
    army_list_id = int(callback.data.split(":")[1])

    army_service = ArmyListService(session)
    success = await army_service.delete_army_list(callback.from_user.id, army_list_id)

    if not success:
        await callback.answer("Не удалось удалить список", show_alert=True)
        return

    await callback.answer("Список удалён!")

    # Показываем оставшиеся списки
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)

    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists)
        )


@router.callback_query(F.data.startswith("refresh_army_list:"))
async def refresh_army_list(callback: CallbackQuery, session: AsyncSession):
    """Обновить список армии из datasources"""
    army_list_id = int(callback.data.split(":")[1])

    army_service = ArmyListService(session)

    success, changes = await army_service.update_army_list_from_datasources(
        callback.from_user.id,
        army_list_id
    )

    if not success:
        await callback.answer("❌ " + "; ".join(changes), show_alert=True)
        return

    # Показываем изменения
    army_list = await army_service.get_army_list(army_list_id)
    stats = await army_service.get_army_list_stats(army_list_id)

    text = format_army_list_full(army_list)

    # Добавляем статистику
    text += "\n\n📊 <b>Статистика:</b>\n"
    if stats["total"] > 0:
        text += f"  🎮 Всего игр: {stats['total']}\n"
        text += f"  ✅ Побед: {stats['wins']}\n"
        text += f"  ❌ Поражений: {stats['losses']}\n"
        if stats["draws"] > 0:
            text += f"  ➖ Ничьих: {stats['draws']}\n"
        text += f"  📈 Винрейт: {stats['win_rate']}%"
    else:
        text += "  <i>Ещё не использовался в играх</i>"

    # Добавляем информацию об обновлении
    text += "\n\n🔄 <b>Результат обновления:</b>\n"
    for change in changes[:10]:  # Максимум 10 изменений
        text += f"  {change}\n"

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=army_list_actions_keyboard(army_list_id)
        )
    except Exception:
        # Если сообщение не изменилось - просто отвечаем
        pass

    await callback.answer("✅ Обновлено!")


@router.callback_query(F.data == "back_to_army_lists")
async def back_to_army_lists(callback: CallbackQuery, session: AsyncSession):
    """Вернуться к списку армий"""
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)

    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists)
        )
    await callback.answer()
