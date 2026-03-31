from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.db import ParticipantRepository
from wh40k_bot.services import GameService, ArmyListService

router = Router()


@router.callback_query(F.data.startswith("show_army_cards:"))
async def show_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки юнитов для списка армии"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card,
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    army_list_id = int(callback.data.split(":")[1])

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)

    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return

    await callback.answer("🎴 Генерирую карточки...")

    status_msg = await callback.message.answer("⏳ Генерация карточек юнитов...")

    try:
        all_cards = []

        # Загружаем данные фракции для Army Rules
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)

        # 1. Army Rules карточка
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)

        # 2. Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)

        # 3. Карточки юнитов
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)

        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return

        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")

        # Отправляем альбомами по 10 карточек
        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]

            media_group = []
            for j, card_bytes in enumerate(batch):
                photo = BufferedInputFile(card_bytes, filename=f"card_{i+j+1}.png")
                media_group.append(InputMediaPhoto(media=photo))

            try:
                await bot.send_media_group(
                    chat_id=callback.from_user.id,
                    media=media_group
                )
            except Exception as e:
                print(f"Error sending batch {i//10 + 1}: {e}")
                continue

        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{army_list.name}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("show_stratagems:"))
async def show_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки стратагем для детачмента армии"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    army_list_id = int(callback.data.split(":")[1])

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)

    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return

    if not army_list.detachment:
        await callback.answer("Детачмент не определён", show_alert=True)
        return

    await callback.answer("🎴 Генерирую стратагемы...")

    status_msg = await callback.message.answer("⏳ Генерация карточек стратагем...")

    try:
        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)

        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return

        cards = generate_stratagems_cards(faction_data, army_list.detachment)

        if not cards:
            await status_msg.edit_text(f"❌ Стратагемы для детачмента '{army_list.detachment}' не найдены")
            return

        await status_msg.edit_text(f"📤 Отправляю {len(cards)} стратагем...")

        # Отправляем альбомами
        for i in range(0, len(cards), 10):
            batch = cards[i:i+10]

            media_group = []
            for j, card_bytes in enumerate(batch):
                photo = BufferedInputFile(card_bytes, filename=f"stratagem_{i+j+1}.png")
                media_group.append(InputMediaPhoto(media=photo))

            try:
                await bot.send_media_group(
                    chat_id=callback.from_user.id,
                    media=media_group
                )
            except Exception as e:
                print(f"Error sending stratagems batch: {e}")
                continue

        await status_msg.edit_text(
            f"✅ Отправлено {len(cards)} стратагем для <b>{army_list.detachment}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("user_army_cards:"))
async def user_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки армии участника (для других игроков)"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card,
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем что пользователь участник игры
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return

    # Получаем участника чьи карточки смотрим
    target_participant = None
    for p in game.participants:
        if p.id == participant_id:
            target_participant = p
            break

    if not target_participant or not target_participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(target_participant.army_list_id)

    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    user = target_participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"

    await callback.answer("🎴 Генерирую карточки...")
    status_msg = await callback.message.answer(f"⏳ Генерация карточек для {user_name}...")

    try:
        all_cards = []

        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)

        # Army Rules
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)

        # Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)

        # Юниты
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)

        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return

        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")

        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"card_{i+j}.png"))
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")

        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{user_name}</b> ({army_list.name})",
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("user_stratagems:"))
async def user_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать стратагемы армии участника (для других игроков)"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем что пользователь участник игры
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return

    # Получаем участника чьи стратагемы смотрим
    target_participant = None
    for p in game.participants:
        if p.id == participant_id:
            target_participant = p
            break

    if not target_participant or not target_participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(target_participant.army_list_id)

    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    if not army_list.faction or not army_list.detachment:
        await callback.answer("Фракция или детачмент не указаны", show_alert=True)
        return

    user = target_participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"

    await callback.answer("⚔️ Генерирую стратагемы...")
    status_msg = await callback.message.answer(f"⏳ Генерация стратагем для {user_name}...")

    try:
        # Загружаем данные фракции
        faction_file = find_faction_file(army_list.faction)
        if not faction_file:
            await status_msg.edit_text("❌ Фракция не найдена в datasources")
            return

        faction_data = load_faction_data(faction_file)
        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return

        # Генерируем карточки стратагем
        stratagem_cards = generate_stratagems_cards(faction_data, army_list.detachment)

        if not stratagem_cards:
            await status_msg.edit_text(
                f"❌ Стратагемы для детачмента <b>{army_list.detachment}</b> не найдены",
                parse_mode="HTML"
            )
            return

        await status_msg.edit_text(f"📤 Отправляю {len(stratagem_cards)} стратагем...")

        # Отправляем альбомами по 10
        for i in range(0, len(stratagem_cards), 10):
            batch = stratagem_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"stratagem_{i+j}.png"))
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")

        await status_msg.edit_text(
            f"✅ Отправлено {len(stratagem_cards)} стратагем для <b>{user_name}</b>\n"
            f"Детачмент: {army_list.detachment}",
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("game_army_cards:"))
@admin_required
async def game_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать меню выбора армии для просмотра карточек"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Создаём клавиатуру с участниками
    buttons = []
    for p in game.participants:
        if p.army_list_id:
            user = p.user
            name = user.username or user.first_name or f"User {user.telegram_id}"

            # Кнопка для карточек юнитов
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎴 {name}",
                    callback_data=f"show_participant_cards:{game.id}:{p.id}"
                ),
                InlineKeyboardButton(
                    text=f"⚔️ Стратагемы",
                    callback_data=f"show_participant_stratagems:{game.id}:{p.id}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_view_game:{game.id}")
    ])

    await callback.message.edit_text(
        f"🎴 <b>Карточки армий для игры</b>\n\n"
        f"Выберите участника для просмотра карточек:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("show_participant_cards:"))
@admin_required
async def show_participant_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать карточки армии участника игры"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card,
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])

    # Получаем участника
    repo = ParticipantRepository(session)
    participant = await repo.get_by_id(participant_id)

    if not participant or not participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(participant.army_list_id)

    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    user = participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"

    await callback.answer("🎴 Генерирую карточки...")
    status_msg = await callback.message.answer(f"⏳ Генерация карточек для {user_name}...")

    try:
        all_cards = []

        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)

        # Army Rules
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)

        # Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)

        # Юниты
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)

        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return

        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")

        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"card_{i+j}.png"))
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")

        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{user_name}</b> ({army_list.name})",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("show_participant_stratagems:"))
@admin_required
async def show_participant_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать стратагемы детачмента участника"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data

    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])

    repo = ParticipantRepository(session)
    participant = await repo.get_by_id(participant_id)

    if not participant or not participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return

    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(participant.army_list_id)

    if not army_list or not army_list.detachment:
        await callback.answer("Детачмент не определён", show_alert=True)
        return

    user = participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"

    await callback.answer("🎴 Генерирую стратагемы...")
    status_msg = await callback.message.answer(f"⏳ Генерация стратагем для {user_name}...")

    try:
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)

        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return

        cards = generate_stratagems_cards(faction_data, army_list.detachment)

        if not cards:
            await status_msg.edit_text(f"❌ Стратагемы для '{army_list.detachment}' не найдены")
            return

        await status_msg.edit_text(f"📤 Отправляю {len(cards)} стратагем...")

        for i in range(0, len(cards), 10):
            batch = cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"strat_{i+j}.png"))
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending stratagems: {e}")

        await status_msg.edit_text(
            f"✅ Отправлено {len(cards)} стратагем для <b>{user_name}</b> ({army_list.detachment})",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
