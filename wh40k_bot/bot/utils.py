from datetime import timedelta

from wh40k_bot.config import config
from wh40k_bot.db import Game, GameParticipant, GameStatus, Team


def _to_local(dt):
    """Конвертировать UTC datetime в локальное время по TIMEZONE_OFFSET"""
    return dt + timedelta(hours=config.timezone_offset)


def _tz_label():
    offset = config.timezone_offset
    if offset == 0:
        return "UTC"
    sign = "+" if offset > 0 else ""
    return f"UTC{sign}{offset}"


def format_game_info(game: Game, detailed: bool = False) -> str:
    """Форматирование информации об игре"""
    if game.title:
        title = f"{game.title} <code>#{game.id}</code>"
    else:
        title = f"Игра <code>#{game.id}</code>"

    # game.status может быть enum или строкой
    status_value = game.status.value if hasattr(game.status, 'value') else game.status

    status_emoji = {
        "collecting": "📝",
        "ready": "✅",
        "in_progress": "⚔️",
        "finished": "🏁",
        "cancelled": "❌",
    }

    status_text = {
        "collecting": "Сбор списков",
        "ready": "Готово к игре",
        "in_progress": "Игра идёт",
        "finished": "Завершена",
        "cancelled": "Отменена",
    }

    emoji = status_emoji.get(status_value, "❓")
    status = status_text.get(status_value, status_value)

    lines = [
        f"{emoji} <b>{title}</b>",
        f"Статус: {status}",
        f"Участники: {game.submitted_count}/{game.total_participants} отправили списки"
    ]
    
    if game.points_limit:
        lines.append(f"🎯 Лимит очков: {game.points_limit}")
    
    if game.deadline:
        lines.append(f"⏰ Дедлайн списков: {_to_local(game.deadline).strftime('%d.%m.%Y %H:%M')} {_tz_label()}")

    if game.scheduled_at:
        lines.append(f"🕐 Дата игры: {_to_local(game.scheduled_at).strftime('%d.%m.%Y %H:%M')} {_tz_label()}")
    
    if game.winner_team:
        winner = "Команда A" if game.winner_team == Team.TEAM_A.value else "Команда B"
        lines.append(f"🏆 Победитель: {winner}")
    
    if detailed:
        lines.append("\n<b>Участники:</b>")
        
        team_a = [p for p in game.participants if p.team == Team.TEAM_A.value]
        team_b = [p for p in game.participants if p.team == Team.TEAM_B.value]
        no_team = [p for p in game.participants if not p.team]
        
        if team_a:
            lines.append("\n🅰️ <b>Команда A:</b>")
            for p in team_a:
                lines.append(format_participant(p))
        
        if team_b:
            lines.append("\n🅱️ <b>Команда B:</b>")
            for p in team_b:
                lines.append(format_participant(p))
        
        if no_team:
            lines.append("\n👥 <b>Без команды:</b>")
            for p in no_team:
                lines.append(format_participant(p))
    
    return "\n".join(lines)


def format_participant(p: GameParticipant) -> str:
    """Форматирование участника"""
    user = p.user
    name = user.username or user.first_name or f"User {user.telegram_id}"
    
    if user.username:
        name = f"@{name}"
    
    status = "✅" if p.army_list_id else "⏳"
    return f"  {status} {name}"


def format_army_lists(game: Game) -> str:
    """Форматирование всех списков армий для рассылки"""
    from wh40k_bot.services.army_list_service import format_army_list_full
    
    title = game.title or f"Игра #{game.id}"
    
    lines = [
        f"⚔️ <b>{title}</b>",
        f"Все списки армий собраны!\n",
        "=" * 30
    ]
    
    # Группируем по командам
    team_a = [p for p in game.participants if p.team == Team.TEAM_A.value]
    team_b = [p for p in game.participants if p.team == Team.TEAM_B.value]
    no_team = [p for p in game.participants if not p.team]
    
    if team_a:
        lines.append("\n🅰️ <b>КОМАНДА A</b>\n")
        for p in team_a:
            lines.append(format_participant_army(p))
    
    if team_b:
        lines.append("\n🅱️ <b>КОМАНДА B</b>\n")
        for p in team_b:
            lines.append(format_participant_army(p))
    
    if no_team:
        if team_a or team_b:
            lines.append("\n👥 <b>БЕЗ КОМАНДЫ</b>\n")
        for p in no_team:
            lines.append(format_participant_army(p))
    
    lines.append("\n" + "=" * 30)
    lines.append("\n<i>Удачной игры! За Императора! (или нет)</i> 🎲")
    
    return "\n".join(lines)


def format_participant_army(p: GameParticipant) -> str:
    """Форматирование армии участника"""
    from wh40k_bot.services.army_list_service import parse_army_list_json
    
    user = p.user
    name = user.username or user.first_name or f"User {user.telegram_id}"
    
    if user.username:
        name = f"@{name}"
    
    lines = [f"<b>👤 {name}</b>"]
    
    if p.army_list:
        try:
            parsed = parse_army_list_json(p.army_list.json_data)
            lines.append(f"📋 <b>{parsed.name}</b>")
            lines.append(f"⚔️ {parsed.faction or 'Unknown'} | {parsed.total_points} pts")
            lines.append("")
            for unit in parsed.units:
                models_str = f" x{unit.models}" if unit.models > 1 else ""
                lines.append(f"  • {unit.name}{models_str} — {unit.points} pts")
        except Exception as e:
            lines.append(f"<i>Ошибка парсинга списка: {e}</i>")
    else:
        lines.append("<i>Список не загружен</i>")
    
    lines.append("")
    return "\n".join(lines)


def format_reminder(game: Game, participant: GameParticipant) -> str:
    """Форматирование напоминания"""
    title = game.title or f"Игра #{game.id}"
    
    lines = [
        f"⏰ <b>Напоминание!</b>",
        f"",
        f"Скоро дедлайн для отправки списка армии в игре <b>{title}</b>!",
        f"",
        f"Дедлайн: {_to_local(game.deadline).strftime('%d.%m.%Y %H:%M')} {_tz_label()}",
        f"",
        f"Отправьте ваш список командой /submit или просто отправьте текст/файл со списком."
    ]
    
    return "\n".join(lines)


def format_game_result(game: Game) -> str:
    """Форматирование результата игры"""
    title = game.title or f"Игра #{game.id}"
    
    winner = "Команда A" if game.winner_team == Team.TEAM_A.value else "Команда B"
    winner_emoji = "🅰️" if game.winner_team == Team.TEAM_A.value else "🅱️"
    
    lines = [
        f"🏁 <b>Игра завершена!</b>",
        f"",
        f"<b>{title}</b>",
        f"",
        f"🏆 Победитель: {winner_emoji} <b>{winner}</b>",
        f"",
        f"<b>Участники:</b>"
    ]
    
    team_a = [p for p in game.participants if p.team == Team.TEAM_A.value]
    team_b = [p for p in game.participants if p.team == Team.TEAM_B.value]
    
    is_winner_a = game.winner_team == Team.TEAM_A.value
    
    lines.append(f"\n{'🏆' if is_winner_a else ''} 🅰️ Команда A:")
    for p in team_a:
        name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
        if p.user.username:
            name = f"@{name}"
        lines.append(f"  • {name}")
    
    lines.append(f"\n{'🏆' if not is_winner_a else ''} 🅱️ Команда B:")
    for p in team_b:
        name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
        if p.user.username:
            name = f"@{name}"
        lines.append(f"  • {name}")
    
    return "\n".join(lines)
