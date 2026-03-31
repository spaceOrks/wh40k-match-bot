import re

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import game_management_keyboard
from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.bot.utils import format_game_info
from wh40k_bot.config import config
from wh40k_bot.db import UserRepository
from wh40k_bot.services import GameService

router = Router()


@router.message(Command("newgame"))
@admin_required
async def cmd_newgame(message: Message, session: AsyncSession, bot: Bot, **kwargs):
    """
    Создать новую игру.

    Формат с kwargs:
    /newgame --user @player1 --user @player2 --name "Битва за Терру" --start 15.02.2026 18:00 --points 2000 --delay 24

    Краткие флаги:
    -u = --user
    -n = --name
    -s = --start
    -p = --points
    -d = --delay

    Старый формат (для совместимости):
    /newgame @user1 @user2 "название" ДД.ММ.ГГГГ ЧЧ:ММ [очки] [дедлайн_часы]
    """
    from datetime import datetime
    import shlex

    text = message.text or ""

    # Определяем формат команды
    is_kwargs_format = '--' in text or ' -u ' in text or ' -n ' in text or ' -p ' in text or ' -d ' in text or ' -s ' in text

    if is_kwargs_format:
        # Новый kwargs формат
        result = await parse_newgame_kwargs(message, session)
    else:
        # Старый формат для совместимости
        result = await parse_newgame_legacy(message, session)

    if result is None:
        return

    participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors = result

    if errors:
        await message.answer(
            f"⚠️ Не удалось найти пользователей: {', '.join(errors)}\n\n"
            "Эти пользователи должны сначала написать боту /start"
        )
        if not participant_ids:
            return

    # Создаём игру
    service = GameService(session)
    result = await service.create_game(
        created_by=message.from_user.id,
        participant_telegram_ids=participant_ids,
        participant_usernames=participant_usernames,
        participant_names=participant_names,
        title=title,
        deadline_hours=deadline_hours,
        scheduled_at=scheduled_at,
        points_limit=points_limit
    )

    game = result.game

    # Отправляем подтверждение админу
    await message.answer(
        f"✅ Игра создана!\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )

    # Уведомляем участников
    for tg_id, name in result.users_to_notify:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=(
                    f"🎮 <b>Вас добавили в игру!</b>\n\n"
                    f"{format_game_info(game)}\n\n"
                    f"Отправьте ваш список армии текстом.\n\n"
                    f"Используйте /submit для отправки списка."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            await message.answer(
                f"⚠️ Не удалось уведомить {name}: {e}"
            )


async def parse_newgame_kwargs(message: Message, session: AsyncSession):
    """Парсинг kwargs формата: --user @p1 --user @p2 --name "X" --start DD.MM.YYYY HH:MM --points 2000 --delay 24"""
    from datetime import datetime
    import shlex

    text = message.text or ""

    # Убираем /newgame
    text = re.sub(r'^/newgame\s*', '', text)

    # Заменяем короткие флаги на длинные (учитываем начало строки и пробелы)
    text = re.sub(r'(^|\s)-u\s', r'\1--user ', text)
    text = re.sub(r'(^|\s)-n\s', r'\1--name ', text)
    text = re.sub(r'(^|\s)-s\s', r'\1--start ', text)
    text = re.sub(r'(^|\s)-p\s', r'\1--points ', text)
    text = re.sub(r'(^|\s)-d\s', r'\1--delay ', text)

    # Парсим аргументы
    users = []
    title = None
    scheduled_at = None
    points_limit = None
    deadline_hours = config.default_deadline_hours

    # Извлекаем --user
    user_matches = re.findall(r'--user\s+@?(\w+)', text)
    users = user_matches

    # Извлекаем --name (в кавычках или без)
    name_match = re.search(r'--name\s+"([^"]+)"', text) or re.search(r'--name\s+(\S+)', text)
    if name_match:
        title = name_match.group(1)

    # Извлекаем --start (дата и время)
    start_match = re.search(r'--start\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})', text)
    if start_match:
        day, month, year, hour, minute = start_match.groups()
        try:
            scheduled_at = datetime(int(year), int(month), int(day), int(hour), int(minute))
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте --start ДД.ММ.ГГГГ ЧЧ:ММ")
            return None

    # Извлекаем --points
    points_match = re.search(r'--points\s+(\d+)', text)
    if points_match:
        points_limit = int(points_match.group(1))

    # Извлекаем --delay
    delay_match = re.search(r'--delay\s+(\d+)', text)
    if delay_match:
        deadline_hours = int(delay_match.group(1))

    if len(users) < 2:
        await message.answer(
            "❌ Укажите минимум 2 участников!\n\n"
            "<b>Формат:</b>\n"
            "<code>/newgame --user @p1 --user @p2 --name \"Название\" --start 15.02.2026 18:00 --points 2000 --delay 24</code>\n\n"
            "<b>Короткие флаги:</b>\n"
            "<code>-u</code> = --user (участник)\n"
            "<code>-n</code> = --name (название)\n"
            "<code>-s</code> = --start (дата и время)\n"
            "<code>-p</code> = --points (лимит очков)\n"
            "<code>-d</code> = --delay (дедлайн в часах)\n\n"
            "<b>Пример:</b>\n"
            "<code>/newgame -u @player1 -u @player2 -n \"Битва\" -p 2000</code>",
            parse_mode="HTML"
        )
        return None

    if len(users) > 10:
        await message.answer("❌ Максимум 10 участников!")
        return None

    # Получаем информацию о пользователях
    participant_ids = []
    participant_usernames = []
    participant_names = []
    errors = []

    user_repo = UserRepository(session)

    for username in users:
        user = await user_repo.get_by_username(username)
        if user:
            participant_ids.append(user.telegram_id)
            participant_usernames.append(user.username)
            participant_names.append(user.first_name)
        else:
            errors.append(f"@{username}")

    return participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors


async def parse_newgame_legacy(message: Message, session: AsyncSession):
    """Парсинг старого формата: /newgame @u1 @u2 "название" ДД.ММ.ГГГГ ЧЧ:ММ [очки] [дедлайн]"""
    from datetime import datetime

    # Парсим упоминания пользователей
    entities = message.entities or []
    mentions = []

    for entity in entities:
        if entity.type == "mention":
            # @username
            username = message.text[entity.offset + 1:entity.offset + entity.length]
            mentions.append({"type": "username", "value": username})
        elif entity.type == "text_mention":
            # Упоминание без username
            mentions.append({
                "type": "user",
                "user_id": entity.user.id,
                "first_name": entity.user.first_name,
                "username": entity.user.username
            })

    if len(mentions) < 2:
        await message.answer(
            "❌ Укажите минимум 2 участников!\n\n"
            "<b>Новый формат (рекомендуется):</b>\n"
            "<code>/newgame -u @p1 -u @p2 -n \"Название\" -p 2000 -d 24</code>\n\n"
            "<b>Старый формат:</b>\n"
            "<code>/newgame @user1 @user2 \"Название\" ДД.ММ.ГГГГ ЧЧ:ММ очки дедлайн</code>\n\n"
            "Используйте /help для подробностей.",
            parse_mode="HTML"
        )
        return None

    if len(mentions) > 10:
        await message.answer("❌ Максимум 10 участников!")
        return None

    # Парсим название и дедлайн
    text = message.text

    # Убираем команду и упоминания
    clean_text = re.sub(r'/newgame\s*', '', text)
    clean_text = re.sub(r'@\w+', '', clean_text).strip()

    title = None
    deadline_hours = config.default_deadline_hours
    scheduled_at = None
    points_limit = None

    # Ищем название в кавычках
    title_match = re.search(r'"([^"]+)"', clean_text)
    if title_match:
        title = title_match.group(1)
        clean_text = clean_text.replace(title_match.group(0), '').strip()

    # Ищем дату и время (ДД.ММ.ГГГГ ЧЧ:ММ)
    datetime_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})', clean_text)
    if datetime_match:
        day, month, year, hour, minute = datetime_match.groups()
        try:
            scheduled_at = datetime(int(year), int(month), int(day), int(hour), int(minute))
            clean_text = clean_text.replace(datetime_match.group(0), '').strip()
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ ЧЧ:ММ")
            return None

    # Ищем числа (points_limit и deadline)
    numbers = re.findall(r'(\d+)', clean_text)
    if len(numbers) >= 2:
        num1, num2 = int(numbers[0]), int(numbers[1])
        if num1 > 100:
            points_limit = num1
            deadline_hours = num2
        else:
            deadline_hours = num1
            if num2 > 100:
                points_limit = num2
    elif len(numbers) == 1:
        num = int(numbers[0])
        if num > 100:
            points_limit = num
        else:
            deadline_hours = num

    # Получаем информацию о пользователях
    participant_ids = []
    participant_usernames = []
    participant_names = []
    errors = []

    user_repo = UserRepository(session)

    for mention in mentions:
        if mention["type"] == "user":
            participant_ids.append(mention["user_id"])
            participant_usernames.append(mention.get("username"))
            participant_names.append(mention.get("first_name"))
        else:
            # Ищем пользователя по username в нашей базе
            username = mention["value"]
            user = await user_repo.get_by_username(username)
            if user:
                participant_ids.append(user.telegram_id)
                participant_usernames.append(user.username)
                participant_names.append(user.first_name)
            else:
                errors.append(f"@{username}")

    return participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors


@router.message(Command("games"))
@admin_required
async def cmd_games(message: Message, session: AsyncSession, **kwargs):
    """Список всех активных игр"""
    service = GameService(session)
    games = await service.get_active_games()

    if not games:
        await message.answer("📭 Нет активных игр")
        return

    text = ["📋 <b>Активные игры:</b>\n"]

    for game in games:
        text.append(format_game_info(game))
        text.append("")

    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(Command("admin"))
@admin_required
async def cmd_admin(message: Message, **kwargs):
    """Админ-панель"""
    text = [
        "🔧 <b>Админ-панель</b>",
        "",
        "<b>Управление играми:</b>",
        "/newgame — создать игру",
        "/games — список активных игр",
        "/game [id] — управление игрой",
        "/users — список пользователей",
        "",
        "<b>Данные:</b>",
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить datasources", callback_data="update_datasources")]
    ])

    await message.answer("\n".join(text), parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("game"))
@admin_required
async def cmd_game(message: Message, session: AsyncSession, **kwargs):
    """Управление конкретной игрой"""
    args = message.text.split()

    if len(args) < 2:
        await message.answer("Использование: /game [id]")
        return

    try:
        game_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await message.answer("❌ Игра не найдена")
        return

    await message.answer(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )


@router.message(Command("users"))
@admin_required
async def cmd_users(message: Message, session: AsyncSession, **kwargs):
    """Список всех зарегистрированных пользователей"""
    repo = UserRepository(session)
    users = await repo.get_all()

    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей")
        return

    text = [f"👥 <b>Зарегистрированные пользователи ({len(users)}):</b>\n"]

    for user in users:
        name = user.username or user.first_name or f"ID {user.telegram_id}"
        if user.username:
            name = f"@{name}"

        is_admin = config.is_admin(user.telegram_id)
        admin_badge = " 👑" if is_admin else ""

        registered = user.created_at.strftime("%d.%m.%Y")

        text.append(f"• {name}{admin_badge} <code>({user.telegram_id})</code> — с {registered}")

    await message.answer("\n".join(text), parse_mode="HTML")
