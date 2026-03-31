from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.middlewares import admin_required

router = Router()


@router.callback_query(F.data == "update_datasources")
@admin_required
async def update_datasources(callback: CallbackQuery, **kwargs):
    """Обновить datasources из git"""
    import subprocess
    import os

    datasources_path = "/app/datasources"

    # Проверяем существует ли директория
    if not os.path.exists(datasources_path):
        await callback.answer("❌ Директория datasources не найдена", show_alert=True)
        return

    await callback.answer("🔄 Обновляю...")

    try:
        # Проверяем есть ли .git
        git_dir = os.path.join(datasources_path, ".git")

        if os.path.exists(git_dir):
            # Есть git - fetch + hard reset (работает и после force push)
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=datasources_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=datasources_path,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            # Нет git - клонируем заново
            # Удаляем содержимое и клонируем
            result = subprocess.run(
                ["git", "clone", "https://github.com/game-datacards/datasources.git", "."],
                cwd=datasources_path,
                capture_output=True,
                text=True,
                timeout=120
            )

        if result.returncode == 0:
            output = result.stdout.strip() or "Already up to date"
            await callback.message.edit_text(
                f"✅ <b>Datasources обновлены!</b>\n\n"
                f"<code>{output[:500]}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить ещё раз", callback_data="update_datasources")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
                ])
            )
        else:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            await callback.message.edit_text(
                f"❌ <b>Ошибка обновления</b>\n\n"
                f"<code>{error[:500]}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="update_datasources")]
                ])
            )
    except subprocess.TimeoutExpired:
        await callback.message.edit_text(
            "❌ <b>Timeout</b>\n\nОбновление заняло слишком много времени.",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Ошибка:</b> {e}",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "back_to_admin")
@admin_required
async def back_to_admin(callback: CallbackQuery, **kwargs):
    """Вернуться в админ-панель"""
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

    await callback.message.edit_text("\n".join(text), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    """Пустой обработчик для информационных кнопок"""
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, session: AsyncSession):
    """Отмена текущего действия"""
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()
