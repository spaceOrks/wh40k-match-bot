from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import (
    army_lists_keyboard,
    confirm_keyboard,
    game_management_keyboard,
    my_games_keyboard,
    team_assignment_keyboard,
    winner_select_keyboard,
)
from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.bot.utils import format_army_lists, format_game_info, format_game_result
from wh40k_bot.db import ParticipantRepository, Team
from wh40k_bot.services import GameService, ArmyListService
from wh40k_bot.config import config

router = Router()


@router.callback_query(F.data.startswith("select_game:"))
async def select_game(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Выбор игры для просмотра"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    is_admin = config.is_admin(callback.from_user.id)

    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game) if is_admin else None
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_my_game:"))
async def view_my_game(callback: CallbackQuery, session: AsyncSession):
    """Просмотр игры пользователем"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем что пользователь участник
    participant = None
    for p in game.participants:
        if p.user.telegram_id == callback.from_user.id:
            participant = p
            break

    if not participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return

    status_value = game.status.value if hasattr(game.status, 'value') else game.status

    # Формируем информацию об игре
    title = game.title or f"Игра #{game.id}"
    lines = [f"🎮 <b>{title}</b>\n"]

    # Статус игры
    status_text = {
        "collecting": "📝 Сбор списков",
        "ready": "✅ Готово к игре",
        "in_progress": "⚔️ Игра идёт",
    }
    lines.append(f"Статус: {status_text.get(status_value, status_value)}")

    if game.scheduled_at:
        lines.append(f"🕐 Дата игры: {game.scheduled_at.strftime('%d.%m.%Y %H:%M')} UTC")

    if game.deadline and status_value == "collecting":
        lines.append(f"⏰ Дедлайн списков: {game.deadline.strftime('%d.%m.%Y %H:%M')} UTC")

    # Ваш статус
    lines.append("")
    if participant.army_list_id:
        lines.append("✅ <b>Вы отправили список</b>")
    else:
        lines.append("⏳ <b>Вы ещё не выбрали список</b>")

    # Участники
    lines.append(f"\n👥 <b>Участники ({game.submitted_count}/{game.total_participants}):</b>")
    for p in game.participants:
        name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
        if p.user.username:
            name = f"@{name}"
        status_icon = "✅" if p.army_list_id else "⏳"
        you_marker = " (вы)" if p.user.telegram_id == callback.from_user.id else ""
        lines.append(f"  {status_icon} {name}{you_marker}")

    # Кнопки действий
    buttons = []

    if status_value == "collecting":
        if not participant.army_list_id:
            buttons.append([
                InlineKeyboardButton(
                    text="📝 Выбрать список",
                    callback_data=f"submit_list:{game.id}"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Изменить список",
                    callback_data=f"resubmit_list:{game.id}"
                )
            ])

    # Показать списки если они собраны
    if status_value in ["ready", "in_progress"]:
        buttons.append([
            InlineKeyboardButton(
                text="📋 Посмотреть все списки",
                callback_data=f"view_all_lists:{game.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к играм",
            callback_data="back_to_mygames"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("submit_list:"))
async def start_submit_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Начать отправку списка для выбранной игры"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    if status_value != "collecting":
        await callback.answer("Приём списков закрыт", show_alert=True)
        return

    # Проверяем есть ли списки армий
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)

    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии из game-datacards\n"
            "(List → Export as Datasource)"
        )
        await callback.answer()
        return

    title = game.title or f"Игра #{game.id}"
    await callback.message.edit_text(
        f"📋 Выберите список армии для игры <b>{title}</b>:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_army_list:"))
async def select_army_list_for_game(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Выбор списка армии для игры"""
    from datetime import datetime

    parts = callback.data.split(":")
    game_id = int(parts[1])
    army_list_id = int(parts[2])

    # Получаем игру для проверки лимита
    game_service = GameService(session)
    game = await game_service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем статус игры
    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    if status_value != "collecting":
        await callback.answer("Приём списков для этой игры закрыт", show_alert=True)
        return

    # Проверяем дедлайн
    if game.deadline and datetime.utcnow() > game.deadline:
        await callback.message.edit_text(
            f"❌ <b>Дедлайн истёк!</b>\n\n"
            f"⏰ Дедлайн был: {game.deadline.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
            f"Приём списков для этой игры закрыт.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_mygames")]
            ])
        )
        await callback.answer("Дедлайн истёк", show_alert=True)
        return

    # Валидируем список перед прикреплением
    army_service = ArmyListService(session)
    is_valid, messages = await army_service.validate_army_list_for_game(army_list_id)

    if not is_valid:
        error_text = "❌ <b>Список армии не прошёл валидацию:</b>\n\n" + "\n".join(f"• {e}" for e in messages[:10])
        await callback.message.edit_text(
            error_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"refresh_army_list:{army_list_id}")],
                [InlineKeyboardButton(text="◀️ Выбрать другой", callback_data=f"submit_list:{game_id}")]
            ])
        )
        await callback.answer("Валидация не пройдена", show_alert=True)
        return

    # Проверяем лимит очков
    army_list = await army_service.get_army_list(army_list_id)
    if game.points_limit and army_list.total_points > game.points_limit:
        await callback.message.edit_text(
            f"❌ <b>Армия превышает лимит очков!</b>\n\n"
            f"🎯 Лимит игры: {game.points_limit} pts\n"
            f"⚔️ Ваша армия: {army_list.total_points} pts\n"
            f"📛 Превышение: {army_list.total_points - game.points_limit} pts\n\n"
            f"Выберите другую армию или уменьшите текущую.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Выбрать другой", callback_data=f"submit_list:{game_id}")]
            ])
        )
        await callback.answer("Армия превышает лимит", show_alert=True)
        return

    # Если есть предупреждения — показываем их
    if messages:
        warning_text = "\n".join(messages)
        await callback.answer(warning_text[:200], show_alert=True)

    result = await game_service.submit_army_list(
        telegram_id=callback.from_user.id,
        game_id=game_id,
        army_list_id=army_list_id
    )

    if not result.success:
        await callback.answer(result.error, show_alert=True)
        return

    await callback.message.edit_text("✅ Список армии отправлен!")
    await callback.answer()

    # Если все отправили — рассылаем всем
    if result.all_submitted:
        game = result.game

        # Формируем текст со всеми списками
        lists_text = format_army_lists(game)

        # Добавляем информацию о дате игры если есть
        scheduled_info = ""
        if game.scheduled_at:
            scheduled_info = f"\n\n🕐 <b>Дата игры:</b> {game.scheduled_at.strftime('%d.%m.%Y %H:%M')} UTC"

        # Рассылаем всем участникам
        for participant in game.participants:
            try:
                await bot.send_message(
                    chat_id=participant.user.telegram_id,
                    text=lists_text + scheduled_info,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Failed to notify {participant.user.telegram_id}: {e}")

        # Уведомляем админа
        try:
            await bot.send_message(
                chat_id=game.created_by,
                text=f"✅ Все списки собраны для игры <b>{game.title or f'#{game.id}'}</b>!",
                parse_mode="HTML",
                reply_markup=game_management_keyboard(game)
            )
        except:
            pass


@router.callback_query(F.data.startswith("resubmit_list:"))
async def resubmit_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Переотправить список армии"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    success = await service.clear_army_list_for_resubmit(callback.from_user.id, game_id)

    if not success:
        await callback.answer("Переотправка недоступна", show_alert=True)
        return

    # Показываем выбор списков
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)

    if not army_lists:
        await callback.message.edit_text(
            "🔄 Ваш предыдущий список удалён.\n\n"
            "📭 У вас нет сохранённых списков армий.\n"
            "Отправьте JSON файл списка армии."
        )
        await callback.answer()
        return

    game = await service.get_game(game_id)
    title = game.title or f"Игра #{game.id}"

    await callback.message.edit_text(
        f"🔄 Ваш предыдущий список удалён.\n\n"
        f"📋 Выберите новый список армии для игры <b>{title}</b>:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("game_status:"))
@admin_required
async def game_status(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать статус списков"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("assign_teams:"))
@admin_required
async def assign_teams(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать интерфейс распределения по командам"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        f"👥 <b>Распределение по командам</b>\n\n"
        f"Нажимайте 🅰️ или 🅱️ для назначения команды:",
        parse_mode="HTML",
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("random_teams:"))
@admin_required
async def random_teams(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Случайно распределить участников по командам"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    await service.auto_assign_teams(game_id)
    await session.commit()

    game = await service.get_game(game_id)

    await callback.message.edit_reply_markup(
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer("🎲 Команды распределены случайно!")


@router.callback_query(F.data.startswith("set_team:"))
@admin_required
async def set_team(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Назначить команду участнику"""
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    team_letter = parts[3]

    team = Team.TEAM_A if team_letter == "A" else Team.TEAM_B

    repo = ParticipantRepository(session)
    await repo.set_team(participant_id, team)
    await session.commit()

    service = GameService(session)
    game = await service.get_game(game_id)

    await callback.message.edit_reply_markup(
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer(f"Назначен в команду {team_letter}")


@router.callback_query(F.data.startswith("teams_done:"))
@admin_required
async def teams_done(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Завершить распределение команд"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем, что все распределены
    unassigned = [p for p in game.participants if not p.team]
    if unassigned:
        names = [p.user.username or p.user.first_name for p in unassigned]
        await callback.answer(
            f"Не распределены: {', '.join(names)}",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("✅ Команды распределены!")


@router.callback_query(F.data.startswith("start_game:"))
@admin_required
async def start_game(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Начать игру"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.mission_service import (
        generate_random_mission, get_mission_images,
        format_mission_info, MissionResult
    )

    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем, есть ли участники без команды
    unassigned = [p for p in game.participants if not p.team]
    auto_assigned = False

    if unassigned:
        # Автоматически распределяем по командам
        await service.auto_assign_teams(game_id)
        await session.commit()
        game = await service.get_game(game_id)
        auto_assigned = True

    # Генерируем миссию
    mission = generate_random_mission()
    if mission:
        game.mission_data = mission.to_dict()
        await session.commit()

    success = await service.start_game(game_id)

    if not success:
        await callback.answer("Не удалось начать игру", show_alert=True)
        return

    game = await service.get_game(game_id)

    auto_text = "\n\n<i>⚠️ Команды были распределены автоматически</i>" if auto_assigned else ""

    # Отправляем миссию всем участникам
    if mission:
        primary_img, deployment_img, terrain_img = get_mission_images(mission)
        mission_text = format_mission_info(mission)

        for participant in game.participants:
            try:
                # Отправляем текст миссии
                await bot.send_message(
                    chat_id=participant.user.telegram_id,
                    text=f"🎮 <b>Игра началась!</b>\n\n{mission_text}",
                    parse_mode="HTML"
                )

                # Отправляем изображения миссии
                media_group = []
                if primary_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(primary_img, "primary_mission.png"),
                        caption="📋 Primary Mission"
                    ))
                if deployment_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(deployment_img, "deployment.png"),
                        caption="🗺 Deployment"
                    ))
                if terrain_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(terrain_img, "terrain_layout.png"),
                        caption="🏔 Terrain Layout"
                    ))

                if media_group:
                    await bot.send_media_group(
                        chat_id=participant.user.telegram_id,
                        media=media_group
                    )
            except Exception as e:
                print(f"Error sending mission to {participant.user.telegram_id}: {e}")

    await callback.message.edit_text(
        f"▶️ <b>Игра началась!</b>{auto_text}\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("Игра началась!")


@router.callback_query(F.data.startswith("record_result:"))
@admin_required
async def record_result(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать выбор победителя"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Показываем состав команд
    team_a = [p for p in game.participants if p.team == Team.TEAM_A.value]
    team_b = [p for p in game.participants if p.team == Team.TEAM_B.value]

    team_a_names = ", ".join(p.user.username or p.user.first_name or "?" for p in team_a)
    team_b_names = ", ".join(p.user.username or p.user.first_name or "?" for p in team_b)

    await callback.message.edit_text(
        f"🏆 <b>Кто победил?</b>\n\n"
        f"🅰️ Команда A: {team_a_names}\n"
        f"🅱️ Команда B: {team_b_names}",
        parse_mode="HTML",
        reply_markup=winner_select_keyboard(game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_winner:"))
@admin_required
async def set_winner(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Установить победителя"""
    parts = callback.data.split(":")
    game_id = int(parts[1])
    winner_letter = parts[2]

    winner_team = Team.TEAM_A if winner_letter == "A" else Team.TEAM_B

    service = GameService(session)
    success = await service.set_winner(game_id, winner_team)

    if not success:
        await callback.answer("Не удалось записать результат", show_alert=True)
        return

    game = await service.get_game(game_id)

    # Уведомляем всех участников
    result_text = format_game_result(game)

    for participant in game.participants:
        try:
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=result_text,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to notify {participant.user.telegram_id}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Результат записан!</b>\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML"
    )
    await callback.answer("Результат записан!")


@router.callback_query(F.data.startswith("cancel_game:"))
@admin_required
async def cancel_game_confirm(callback: CallbackQuery, **kwargs):
    """Подтверждение отмены игры"""
    game_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "❓ <b>Вы уверены, что хотите отменить игру?</b>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("cancel_game", game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel_game:"))
@admin_required
async def cancel_game(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Отменить игру"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Уведомляем участников
    title = game.title or f"Игра #{game.id}"
    for participant in game.participants:
        try:
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=f"❌ Игра <b>{title}</b> отменена.",
                parse_mode="HTML"
            )
        except:
            pass

    success = await service.cancel_game(game_id)

    if not success:
        await callback.answer("Не удалось отменить игру", show_alert=True)
        return

    await callback.message.edit_text(
        f"❌ <b>Игра отменена</b>\n\n{format_game_info(game)}",
        parse_mode="HTML"
    )
    await callback.answer("Игра отменена")


@router.callback_query(F.data.startswith("view_all_lists:"))
async def view_all_lists(callback: CallbackQuery, session: AsyncSession):
    """Просмотр всех списков армий с возможностью генерации карточек"""
    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    # Проверяем что пользователь участник
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return

    lists_text = format_army_lists(game)

    # Создаём кнопки для каждого участника с армией
    buttons = []
    for p in game.participants:
        if p.army_list_id and p.army_list:
            name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
            army_name = p.army_list.name[:20]

            # Кнопки карточек и стратагем в одном ряду
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎴 {name}",
                    callback_data=f"user_army_cards:{game.id}:{p.id}"
                ),
                InlineKeyboardButton(
                    text=f"⚔️ Стратагемы",
                    callback_data=f"user_stratagems:{game.id}:{p.id}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к игре", callback_data=f"view_my_game:{game.id}")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        lists_text + "\n\n<i>Нажмите для просмотра карточек:</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_mygames")
async def back_to_mygames(callback: CallbackQuery, session: AsyncSession):
    """Вернуться к списку игр"""
    service = GameService(session)
    all_games = await service.get_all_active_games_for_user(callback.from_user.id)

    if not all_games:
        await callback.message.edit_text("📭 У вас нет активных игр.")
        await callback.answer()
        return

    pending = sum(1 for p in all_games if not p.army_list_id and (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) == "collecting")
    ready = sum(1 for p in all_games if (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) in ["ready", "in_progress"])

    text = f"🎮 <b>Ваши активные игры ({len(all_games)}):</b>\n\n"
    if pending > 0:
        text += f"⏳ Ожидают ваш список: {pending}\n"
    if ready > 0:
        text += f"⚔️ Готовы к игре: {ready}\n"
    text += "\nНажмите на игру для подробностей:"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=my_games_keyboard(all_games)
    )
    await callback.answer()
