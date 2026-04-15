import asyncio
import subprocess
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from wh40k_bot.bot.utils import format_reminder
from wh40k_bot.config import config
from wh40k_bot.services import ReminderService

DATASOURCES_PATH = "/app/datasources"
DATASOURCES_UPDATE_INTERVAL = 24 * 60 * 60  # раз в сутки


class ReminderScheduler:
    """Планировщик напоминаний о дедлайнах"""
    
    def __init__(self, bot: Bot, session_maker: async_sessionmaker):
        self.bot = bot
        self.session_maker = session_maker
        self._task: asyncio.Task | None = None
        self._running = False
    
    async def start(self):
        """Запустить планировщик"""
        self._running = True
        self._task = asyncio.create_task(self._run())
    
    async def stop(self):
        """Остановить планировщик"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _run(self):
        """Основной цикл"""
        tick = 0
        while self._running:
            try:
                await self._check_reminders()
                await self._check_expired()
                await self._check_game_reminders()

                # Обновляем datasources раз в сутки
                if tick % (DATASOURCES_UPDATE_INTERVAL // 300) == 0:
                    await self._update_datasources()
            except Exception as e:
                print(f"Reminder scheduler error: {e}")

            tick += 1
            # Проверяем каждые 5 минут
            await asyncio.sleep(300)
    
    async def _check_reminders(self):
        """Проверить и отправить напоминания"""
        async with self.session_maker() as session:
            service = ReminderService(session)
            games = await service.get_games_needing_reminder(
                hours_before=config.reminder_before_hours
            )
            
            for game in games:
                # Отправляем напоминания только тем, кто не отправил список
                for participant in game.participants:
                    if participant.army_list_id:
                        continue  # Уже отправил
                    
                    try:
                        await self.bot.send_message(
                            chat_id=participant.user.telegram_id,
                            text=format_reminder(game, participant),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Failed to send reminder to {participant.user.telegram_id}: {e}")
                
                # Отмечаем, что напоминание отправлено
                await service.mark_reminder_sent(game.id)
    
    async def _check_expired(self):
        """Проверить игры с истёкшим дедлайном"""
        async with self.session_maker() as session:
            service = ReminderService(session)
            games = await service.get_expired_games()
            
            for game in games:
                # Уведомляем админа
                missing = [
                    p.user.username or p.user.first_name 
                    for p in game.participants 
                    if not p.army_list_id
                ]
                
                if missing:
                    try:
                        title = game.title or f"Игра #{game.id}"
                        await self.bot.send_message(
                            chat_id=game.created_by,
                            text=(
                                f"⏰ <b>Дедлайн истёк!</b>\n\n"
                                f"Игра: <b>{title}</b>\n"
                                f"Не отправили списки: {', '.join(missing)}\n\n"
                                f"Используйте /game {game.id} для управления игрой."
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Failed to notify admin {game.created_by}: {e}")
    
    async def _check_game_reminders(self):
        """Проверить и отправить напоминания о начале игры (за 2 часа)"""
        async with self.session_maker() as session:
            service = ReminderService(session)
            games = await service.get_games_needing_game_reminder(hours_before=2)
            
            for game in games:
                title = game.title or f"Игра #{game.id}"
                scheduled_str = game.scheduled_at.strftime('%d.%m.%Y %H:%M') if game.scheduled_at else "скоро"
                
                for participant in game.participants:
                    try:
                        await self.bot.send_message(
                            chat_id=participant.user.telegram_id,
                            text=(
                                f"⏰ <b>Напоминание об игре!</b>\n\n"
                                f"Игра <b>{title}</b> начнётся через 2 часа!\n"
                                f"🕐 Время: {scheduled_str} UTC\n\n"
                                f"Не забудьте подготовиться! ⚔️"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Failed to send game reminder to {participant.user.telegram_id}: {e}")
                
                await service.mark_game_reminder_sent(game.id)

    async def _update_datasources(self):
        """Обновить datasources через git pull"""
        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=DATASOURCES_PATH,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print(f"Datasources updated: {result.stdout.strip()}")
            else:
                print(f"Datasources update failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"Datasources update error: {e}")
