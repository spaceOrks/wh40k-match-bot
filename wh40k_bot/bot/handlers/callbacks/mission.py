from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import game_management_keyboard
from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.services import GameService

router = Router()


@router.callback_query(F.data.startswith("show_mission:"))
@admin_required
async def show_mission(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать текущую миссию игры"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.mission_service import (
        get_mission_images, format_mission_info, MissionResult
    )

    game_id = int(callback.data.split(":")[1])

    service = GameService(session)
    game = await service.get_game(game_id)

    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return

    if not game.mission_data:
        await callback.answer("Миссия не назначена", show_alert=True)
        return

    mission = MissionResult.from_dict(game.mission_data)
    mission_text = format_mission_info(mission)

    await callback.message.answer(mission_text, parse_mode="HTML")

    # Отправляем изображения
    primary_img, deployment_img, terrain_img = get_mission_images(mission)

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
            chat_id=callback.from_user.id,
            media=media_group
        )

    await callback.answer()


@router.callback_query(F.data.startswith("regenerate_mission:"))
@admin_required
async def regenerate_mission(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Перегенерировать миссию и отправить всем участникам"""
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

    # Генерируем новую миссию
    mission = generate_random_mission()
    if not mission:
        await callback.answer("Не удалось сгенерировать миссию", show_alert=True)
        return

    # Сохраняем
    game.mission_data = mission.to_dict()
    await session.commit()

    mission_text = format_mission_info(mission)
    primary_img, deployment_img, terrain_img = get_mission_images(mission)

    # Отправляем всем участникам
    sent_count = 0
    for participant in game.participants:
        try:
            # Отправляем текст миссии
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=f"🔄 <b>Миссия перегенерирована!</b>\n\n{mission_text}",
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

            sent_count += 1
        except Exception as e:
            print(f"Error sending mission to {participant.user.telegram_id}: {e}")

    await callback.message.edit_text(
        f"🔄 <b>Миссия перегенерирована!</b>\n\n"
        f"{mission_text}\n\n"
        f"✅ Отправлено {sent_count}/{len(game.participants)} участникам",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("Миссия перегенерирована!")
