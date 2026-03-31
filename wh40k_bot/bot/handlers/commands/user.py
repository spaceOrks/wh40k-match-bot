from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import pending_games_keyboard, resubmit_games_keyboard, my_games_keyboard, army_lists_keyboard
from wh40k_bot.bot.states import SubmitArmyList, UploadArmyList
from wh40k_bot.config import config
from wh40k_bot.db import UserRepository
from wh40k_bot.services import GameService, ArmyListService, format_army_list_full

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    """Команда /start"""
    # Регистрируем пользователя
    repo = UserRepository(session)
    await repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    await session.commit()

    text = [
        "⚔️ <b>WH40K Army List Bot</b>",
        "",
        "Бот для сбора списков армий перед матчами.",
        "",
        "<b>Доступные команды:</b>",
        "/mygames — ваши активные игры",
        "/mylists — ваши списки армий",
        "/submit — отправить список армии для игры",
        "/resubmit — переотправить список",
    ]

    # Добавляем админ-команды если это админ
    if message.from_user.id in config.admin_ids:
        text.extend([
            "",
            "<b>Админ-команды:</b>",
            "/admin — админ-панель",
            "/newgame — создать игру",
            "/games — список игр",
            "/game [id] — управление игрой",
            "/users — список пользователей",
        ])

    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(Command("mygames"))
async def cmd_mygames(message: Message, session: AsyncSession):
    """Мои активные игры"""
    service = GameService(session)
    all_games = await service.get_all_active_games_for_user(message.from_user.id)

    if not all_games:
        await message.answer(
            "📭 У вас нет активных игр.\n"
            "Когда админ добавит вас в игру, вы получите уведомление."
        )
        return

    # Считаем статистику
    pending = sum(1 for p in all_games if not p.army_list_id and (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) == "collecting")
    ready = sum(1 for p in all_games if (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) in ["ready", "in_progress"])

    text = f"🎮 <b>Ваши активные игры ({len(all_games)}):</b>\n\n"
    if pending > 0:
        text += f"⏳ Ожидают ваш список: {pending}\n"
    if ready > 0:
        text += f"⚔️ Готовы к игре: {ready}\n"
    text += "\nНажмите на игру для подробностей:"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=my_games_keyboard(all_games)
    )


@router.message(Command("submit"))
async def cmd_submit(message: Message, session: AsyncSession, state: FSMContext):
    """Начать отправку списка армии"""
    service = GameService(session)
    pending = await service.get_pending_games_for_user(message.from_user.id)

    if not pending:
        await message.answer("📭 У вас нет игр, ожидающих список армии.")
        return

    # Проверяем есть ли у пользователя сохранённые списки
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(message.from_user.id)

    if not army_lists:
        await message.answer(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Сначала загрузите список командой /mylists\n"
            "или отправьте JSON файл прямо сейчас."
        )
        return

    if len(pending) == 1:
        # Если игра одна — сразу показываем выбор списка
        game = pending[0].game
        title = game.title or f"Игра #{game.id}"

        await message.answer(
            f"📋 Выберите список армии для игры <b>{title}</b>:",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game.id)
        )
    else:
        # Если игр несколько — показываем выбор игры
        await message.answer(
            "📋 Выберите игру:",
            reply_markup=pending_games_keyboard(pending)
        )


@router.message(Command("mylists"))
async def cmd_mylists(message: Message, session: AsyncSession):
    """Показать сохранённые списки армий"""
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(message.from_user.id)

    if not army_lists:
        await message.answer(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии из game-datacards\n"
            "(List → Export as Datasource)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
        return

    await message.answer(
        f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>\n\n"
        "Нажмите на список для подробностей:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists)
    )


@router.message(Command("resubmit"))
async def cmd_resubmit(message: Message, session: AsyncSession):
    """Переотправить список армии"""
    service = GameService(session)
    submitted = await service.get_submitted_games_for_user(message.from_user.id)

    if not submitted:
        await message.answer(
            "📭 Нет игр для переотправки.\n"
            "Переотправить можно только пока идёт сбор списков."
        )
        return

    await message.answer(
        "🔄 <b>Выберите игру для переотправки списка:</b>\n\n"
        "⚠️ Ваш текущий список будет удалён!",
        parse_mode="HTML",
        reply_markup=resubmit_games_keyboard(submitted)
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка"""
    is_admin = config.is_admin(message.from_user.id)

    text = [
        "📖 <b>Справка по WH40K Army List Bot</b>",
        "",
        "<b>Как это работает:</b>",
        "1. Загрузите список армии (JSON из game-datacards)",
        "2. Админ создаёт игру и указывает участников",
        "3. Каждый участник получает уведомление",
        "4. Участники выбирают список армии для игры",
        "5. Когда все выбрали — бот рассылает все списки всем",
        "6. После игры админ записывает результат",
        "",
        "<b>Команды для всех:</b>",
        "/start — начать работу с ботом",
        "/mygames — ваши активные игры",
        "/mylists — ваши списки армий",
        "/submit — отправить список армии для игры",
        "/resubmit — переотправить список армии",
        "/help — эта справка",
        "",
        "<i>💡 Для загрузки списка армии отправьте JSON файл</i>",
        "<i>из game-datacards (List → Export as Datasource)</i>",
    ]

    if is_admin:
        text.extend([
            "",
            "<b>Команды для админов:</b>",
            "/newgame — создать игру",
            "",
            "<b>Формат /newgame:</b>",
            "<code>/newgame -u @p1 -u @p2 -n \"Название\" -p 2000 -s 15.02.2026 18:00 -d 24</code>",
            "",
            "Флаги:",
            "  <code>-u</code> / <code>--user</code> — участник (минимум 2)",
            "  <code>-n</code> / <code>--name</code> — название игры",
            "  <code>-p</code> / <code>--points</code> — лимит очков",
            "  <code>-s</code> / <code>--start</code> — дата и время",
            "  <code>-d</code> / <code>--delay</code> — дедлайн (часы)",
            "",
            "/games — все активные игры",
            "/game [id] — управление игрой",
            "/users — список пользователей",
        ])

    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(F.document)
async def process_army_list_file(message: Message, session: AsyncSession, bot: Bot, state: FSMContext):
    """Обработка загруженного JSON файла со списком армии"""
    document = message.document

    # Проверяем что это JSON
    if not document.file_name.endswith('.json'):
        await message.answer("❌ Пожалуйста, отправьте JSON файл (.json)")
        return

    # Скачиваем файл
    try:
        file = await bot.get_file(document.file_id)
        file_content = await bot.download_file(file.file_path)
        json_str = file_content.read().decode('utf-8')
    except Exception as e:
        await message.answer(f"❌ Ошибка при скачивании файла: {e}")
        return

    # Создаём список армии
    army_service = ArmyListService(session)
    try:
        army_list = await army_service.create_army_list(message.from_user.id, json_str)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении: {e}")
        return

    if not army_list:
        await message.answer("❌ Ошибка: пользователь не найден. Напишите /start")
        return

    await message.answer(
        f"✅ Список армии сохранён!\n\n"
        f"{format_army_list_full(army_list)}",
        parse_mode="HTML"
    )
