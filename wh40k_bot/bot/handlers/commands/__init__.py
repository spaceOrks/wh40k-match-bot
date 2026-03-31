from aiogram import Router
from wh40k_bot.bot.handlers.commands.user import router as user_router
from wh40k_bot.bot.handlers.commands.admin import router as admin_router

router = Router()
router.include_router(user_router)
router.include_router(admin_router)
