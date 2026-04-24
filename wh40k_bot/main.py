import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from wh40k_bot.bot import AdminMiddleware, DatabaseMiddleware, setup_routers
from wh40k_bot.config import config
from wh40k_bot.db import create_db_engine, create_session_maker, init_db
from wh40k_bot.scheduler import ReminderScheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def setup_commands(bot: Bot) -> None:
    user_commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="mygames", description="Ваши активные игры"),
        BotCommand(command="mylists", description="Ваши списки армий"),
        BotCommand(command="submit", description="Отправить список армии для игры"),
        BotCommand(command="resubmit", description="Переотправить список армии"),
        BotCommand(command="help", description="Справка"),
    ]
    admin_commands = user_commands + [
        BotCommand(command="newgame", description="Создать игру"),
        BotCommand(command="games", description="Список активных игр"),
        BotCommand(command="game", description="Управление игрой"),
        BotCommand(command="users", description="Список пользователей"),
        BotCommand(command="admin", description="Админ-панель"),
    ]

    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            pass


async def main():
    """Главная функция запуска бота"""
    
    # Проверяем конфигурацию
    if not config.bot_token:
        raise ValueError("BOT_TOKEN не установлен!")
    
    if not config.admin_ids:
        logger.warning("ADMIN_IDS не установлен! Никто не сможет создавать игры.")
    
    # Инициализация БД
    logger.info("Initializing database...")
    engine = await create_db_engine(config.db_url)
    await init_db(engine)
    session_maker = await create_session_maker(engine)
    
    # Инициализация Redis storage для FSM
    logger.info("Connecting to Redis...")
    storage = RedisStorage.from_url(config.redis_url)
    
    # Инициализация бота
    session = None
    if config.proxy_url:
        session = AiohttpSession(proxy=config.proxy_url)
        session._connector_init["ssl"] = False

    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=storage)
    
    # Регистрация middleware
    dp.message.middleware(DatabaseMiddleware(session_maker))
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware(session_maker))
    dp.callback_query.middleware(AdminMiddleware())
    
    # Регистрация роутеров
    main_router = setup_routers()
    dp.include_router(main_router)
    
    # Запуск планировщика напоминаний
    scheduler = ReminderScheduler(bot, session_maker)
    
    # Регистрация команд в меню Telegram
    await setup_commands(bot)

    try:
        logger.info("Starting bot...")
        await scheduler.start()
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await scheduler.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
