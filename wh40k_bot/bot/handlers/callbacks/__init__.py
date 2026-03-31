from aiogram import Router
from wh40k_bot.bot.handlers.callbacks.game import router as game_router
from wh40k_bot.bot.handlers.callbacks.army_list import router as army_list_router
from wh40k_bot.bot.handlers.callbacks.cards import router as cards_router
from wh40k_bot.bot.handlers.callbacks.mission import router as mission_router
from wh40k_bot.bot.handlers.callbacks.admin import router as admin_router

router = Router()
router.include_router(game_router)
router.include_router(army_list_router)
router.include_router(cards_router)
router.include_router(mission_router)
router.include_router(admin_router)
