"""
Сервис для работы с datasources (официальные данные об армиях).
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

DATASOURCES_PATH = "/app/datasources/10th/gdc"

# Маппинг фракций/под-фракций к файлам datasources
# Ключ - название фракции из JSON (lowercase), значение - имя файла без .json
FACTION_FILE_MAPPING = {
    # Space Marines
    "adeptus astartes": "space_marines",
    "ultramarines": "space_marines",
    "iron hands": "space_marines",
    "white scars": "space_marines",
    "imperial fists": "space_marines",
    "salamanders": "space_marines",
    "raven guard": "space_marines",
    "black templars": "blacktemplar",
    "dark angels": "darkangels",
    "blood angels": "bloodangels",
    "space wolves": "spacewolves",
    "deathwatch": "deathwatch",
    "grey knights": "greyknights",
    # Chaos Space Marines
    "heretic astartes": "chaos_spacemarines",
    "chaos space marines": "chaos_spacemarines",
    "world eaters": "worldeaters",
    "death guard": "deathguard",
    "thousand sons": "thousandsons",
    "emperor's children": "emperors_children",
    # Imperium
    "adepta sororitas": "adeptasororitas",
    "adeptus custodes": "adeptuscustodes",
    "adeptus mechanicus": "adeptusmechanicus",
    "astra militarum": "astramilitarum",
    "imperial knights": "imperialknights",
    "imperial agents": "agents",
    # Xenos
    "aeldari": "aeldari",
    "drukhari": "drukhari",
    "genestealer cults": "gsc",
    "leagues of votann": "votann",
    "necrons": "necrons",
    "orks": "orks",
    "t'au empire": "tau",
    "tyranids": "tyranids",
    # Chaos
    "chaos daemons": "chaosdaemons",
    "chaos knights": "chaosknights",
}

# Обратный маппинг: какое отображаемое имя фракции использовать для файла
FACTION_DISPLAY_NAMES = {
    "space_marines": "Space Marines",
    "blacktemplar": "Black Templars",
    "bloodangels": "Blood Angels",
    "darkangels": "Dark Angels",
    "spacewolves": "Space Wolves",
    "deathwatch": "Deathwatch",
    "greyknights": "Grey Knights",
    "chaos_spacemarines": "Chaos Space Marines",
    "worldeaters": "World Eaters",
    "deathguard": "Death Guard",
    "thousandsons": "Thousand Sons",
    "emperors_children": "Emperor's Children",
    "adeptasororitas": "Adepta Sororitas",
    "adeptuscustodes": "Adeptus Custodes",
    "adeptusmechanicus": "Adeptus Mechanicus",
    "astramilitarum": "Astra Militarum",
    "imperialknights": "Imperial Knights",
    "agents": "Imperial Agents",
    "aeldari": "Aeldari",
    "drukhari": "Drukhari",
    "gsc": "Genestealer Cults",
    "votann": "Leagues of Votann",
    "necrons": "Necrons",
    "orks": "Orks",
    "tau": "T'au Empire",
    "tyranids": "Tyranids",
    "chaosdaemons": "Chaos Daemons",
    "chaosknights": "Chaos Knights",
}


def get_datasources_version() -> Optional[str]:
    """Получить версию datasources (дату последнего коммита или время модификации)"""
    import subprocess
    
    datasources_root = "/app/datasources"
    
    # Пробуем получить хэш последнего коммита
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=datasources_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    # Fallback — дата модификации директории
    try:
        import os
        from datetime import datetime
        mtime = os.path.getmtime(DATASOURCES_PATH)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except:
        pass
    
    return None


@dataclass
class ValidationResult:
    """Результат валидации списка армии"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    faction: Optional[str] = None
    detachment: Optional[str] = None
    total_points: int = 0
    has_warlord: bool = False


def get_available_factions() -> List[str]:
    """Получить список доступных фракций"""
    factions = []
    
    if not os.path.exists(DATASOURCES_PATH):
        return factions
    
    for filename in os.listdir(DATASOURCES_PATH):
        if filename.endswith('.json'):
            faction_name = filename.replace('.json', '')
            factions.append(faction_name)
    
    return sorted(factions)


def load_faction_data(faction_id: str) -> Optional[Dict]:
    """Загрузить данные фракции из datasources"""
    # Пробуем разные варианты имени файла
    possible_names = [
        f"{faction_id}.json",
        f"{faction_id.lower()}.json",
        f"{faction_id.replace(' ', '_')}.json",
        f"{faction_id.replace(' ', '-')}.json",
    ]
    
    for name in possible_names:
        filepath = os.path.join(DATASOURCES_PATH, name)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                continue
    
    return None


def find_faction_file(faction_name: str) -> Optional[str]:
    """Найти файл фракции по имени. Использует маппинг для под-фракций."""
    if not os.path.exists(DATASOURCES_PATH):
        return None
    
    # Нормализуем апострофы перед любым сравнением
    faction_lower = _normalize_apostrophes(faction_name).lower().strip()

    # Сначала проверяем маппинг (для под-фракций типа Ultramarines -> space_marines)
    if faction_lower in FACTION_FILE_MAPPING:
        mapped_file = FACTION_FILE_MAPPING[faction_lower]
        if os.path.exists(os.path.join(DATASOURCES_PATH, f"{mapped_file}.json")):
            return mapped_file

    # Затем пробуем прямое совпадение с файлами (стрипаем все спецсимволы)
    def _normalize(s):
        s = _normalize_apostrophes(s).lower()
        return s.replace(' ', '').replace('-', '').replace('_', '').replace("'", '')

    faction_normalized = _normalize(faction_lower)

    for filename in os.listdir(DATASOURCES_PATH):
        if filename.endswith('.json'):
            file_faction = _normalize(filename.replace('.json', ''))
            if file_faction == faction_normalized or faction_normalized in file_faction or file_faction in faction_normalized:
                return filename.replace('.json', '')

    return None


def get_display_faction_name(faction_file: str) -> str:
    """Получить отображаемое имя фракции по имени файла"""
    return FACTION_DISPLAY_NAMES.get(faction_file, faction_file.replace('_', ' ').title())


def get_faction_units(faction_data: Dict) -> Dict[str, Dict]:
    """Извлечь все юниты фракции с их данными"""
    units = {}
    
    datasheets = faction_data.get('datasheets', [])
    
    for unit in datasheets:
        unit_name = unit.get('name', '').strip()
        if unit_name:
            units[unit_name.lower()] = unit
    
    return units


def validate_army_list(json_data, check_on_attach: bool = False) -> ValidationResult:
    """
    Валидировать список армии по datasources.
    Каждый юнит должен ПОЛНОСТЬЮ совпадать с официальными данными.
    
    Args:
        json_data: JSON строка или dict
        check_on_attach: True если проверяем при прикреплении к игре (строже)
    
    Проверяет:
    - Все юниты существуют и совпадают с datasources
    - Есть warlord
    - Все энхансменты из одного detachment
    - Подсчитывает очки включая энхансменты
    """
    errors = []
    warnings = []
    faction = None
    detachment = None
    total_points = 0
    has_warlord = False
    
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            return ValidationResult(valid=False, errors=[f"Невалидный JSON: {e}"], warnings=[])
    else:
        data = json_data
    
    # Получаем датащиты из списка
    if "data" not in data or len(data["data"]) == 0:
        return ValidationResult(valid=False, errors=["Не найдены данные армии в JSON"], warnings=[])
    
    roster = data["data"][0]
    datasheets = roster.get("datasheets", [])
    
    if not datasheets:
        return ValidationResult(valid=False, errors=["Список армии пуст"], warnings=[])
    
    # Определяем фракцию из первого юнита
    for unit in datasheets:
        factions = unit.get("factions", [])
        if factions:
            faction = factions[0]
            break
    
    if not faction:
        return ValidationResult(valid=False, errors=["Не удалось определить фракцию"], warnings=[])
    
    # Ищем файл фракции
    faction_file = find_faction_file(faction)
    
    if not faction_file:
        return ValidationResult(
            valid=False, 
            errors=[f"Фракция '{faction}' не найдена в datasources"], 
            warnings=[], 
            faction=faction
        )
    
    # Используем красивое отображаемое имя фракции
    display_faction = get_display_faction_name(faction_file)
    
    # Загружаем данные фракции
    faction_data = load_faction_data(faction_file)
    
    if not faction_data:
        return ValidationResult(
            valid=False, 
            errors=[f"Не удалось загрузить данные фракции '{display_faction}'"], 
            warnings=[], 
            faction=display_faction
        )
    
    # Получаем официальные юниты
    official_units = get_faction_units(faction_data)
    
    # Собираем информацию об энхансментах
    enhancements = []
    enhancement_detachments = set()
    
    # Проверяем каждый юнит в списке
    for i, unit in enumerate(datasheets):
        unit_name = unit.get("name", "").strip()
        if not unit_name:
            errors.append(f"Юнит #{i+1}: отсутствует имя")
            continue
        
        unit_name_lower = unit_name.lower()
        
        # Проверяем warlord
        if unit.get("isWarlord"):
            has_warlord = True
        
        # Проверяем энхансмент
        enhancement = unit.get("selectedEnhancement")
        if enhancement:
            enh_name = enhancement.get("name", "Unknown")
            enh_cost = int(enhancement.get("cost", 0))
            enh_detachment = enhancement.get("detachment")
            
            enhancements.append({
                "name": enh_name,
                "cost": enh_cost,
                "detachment": enh_detachment,
                "unit": unit_name
            })
            
            total_points += enh_cost
            
            if enh_detachment:
                enhancement_detachments.add(enh_detachment)
                if detachment is None:
                    detachment = enh_detachment
        
        # Ищем официальные данные юнита
        official_unit = None
        
        if unit_name_lower in official_units:
            official_unit = official_units[unit_name_lower]
        else:
            # Пробуем частичное совпадение
            for official_name in official_units.keys():
                if unit_name_lower in official_name or official_name in unit_name_lower:
                    official_unit = official_units[official_name]
                    break
        
        if not official_unit:
            errors.append(f"Юнит '{unit_name}' не найден в datasources")
            continue
        
        # Считаем очки юнита
        unit_size = unit.get("unitSize", {})
        if unit_size and "cost" in unit_size:
            total_points += int(unit_size["cost"])
        elif "points" in unit and len(unit["points"]) > 0:
            for pt in unit["points"]:
                if pt.get("active", True):
                    total_points += int(pt.get("cost", 0))
                    break
        
        # Строгая проверка — сравниваем все важные поля
        unit_errors = validate_unit_strict(unit, official_unit, unit_name)
        errors.extend(unit_errors)
    
    # Проверяем наличие warlord
    if not has_warlord:
        errors.append("В списке отсутствует Warlord (ни один юнит не отмечен как isWarlord)")
    
    # Проверяем что все энхансменты из одного detachment
    if len(enhancement_detachments) > 1:
        detachments_str = ", ".join(enhancement_detachments)
        errors.append(f"Энхансменты из разных detachments: {detachments_str}. Все должны быть из одного.")
    
    # Проверяем на дублирование энхансментов
    enhancement_names = [e["name"] for e in enhancements]
    duplicate_enhancements = [name for name in set(enhancement_names) if enhancement_names.count(name) > 1]
    if duplicate_enhancements:
        errors.append(f"Дублирующиеся энхансменты: {', '.join(duplicate_enhancements)}. Каждый энхансмент можно взять только один раз.")
    
    if errors:
        return ValidationResult(
            valid=False, 
            errors=errors, 
            warnings=warnings, 
            faction=display_faction,
            detachment=detachment,
            total_points=total_points,
            has_warlord=has_warlord
        )
    
    return ValidationResult(
        valid=True, 
        errors=[], 
        warnings=warnings, 
        faction=display_faction,
        detachment=detachment,
        total_points=total_points,
        has_warlord=has_warlord
    )


_UI_FIELDS = {
    "active", "showAbility", "showDescription", "showAtTop", "showInfo",
    "showInvulnerableSave", "showDamagedMarker", "showName", "showDamagedAbility",
}

# Все варианты апострофа → ASCII '
_APOSTROPHE_CHARS = "\u2019\u2018\u02bc\u02b9\u0060\u00b4"


def _normalize_apostrophes(s: str) -> str:
    for ch in _APOSTROPHE_CHARS:
        s = s.replace(ch, "'")
    return s


def _strip_ui(obj):
    """Рекурсивно удалить UI-поля из объекта перед сравнением с datasources."""
    if isinstance(obj, dict):
        return {k: _strip_ui(v) for k, v in obj.items() if k not in _UI_FIELDS}
    if isinstance(obj, list):
        return [_strip_ui(i) for i in obj]
    return obj


def validate_unit_strict(user_unit: dict, official_unit: dict, unit_name: str) -> List[str]:
    """
    Строгая валидация юнита — все поля должны совпадать с официальными.
    Возвращает список ошибок.
    """
    errors = []
    
    # Поля которые должны полностью совпадать
    fields_to_check = [
        ("stats", "характеристики"),
        ("rangedWeapons", "стрелковое оружие"),
        ("meleeWeapons", "рукопашное оружие"),
        ("abilities", "способности"),
        ("keywords", "ключевые слова"),
        ("composition", "состав"),
        ("loadout", "снаряжение"),
        ("wargear", "варгир"),
        ("points", "очки"),
    ]
    
    for field, field_name in fields_to_check:
        user_value = user_unit.get(field)
        official_value = official_unit.get(field)

        if field == "points":
            if not compare_points(user_value, official_value):
                user_pts = extract_points_info(user_value)
                official_pts = extract_points_info(official_value)
                errors.append(f"'{unit_name}': неверные {field_name} (указано: {user_pts}, должно: {official_pts})")
            continue

        if _strip_ui(user_value) != _strip_ui(official_value):
            # Детализируем ошибку
            if field == "points":
                user_pts = extract_points_info(user_value)
                official_pts = extract_points_info(official_value)
                errors.append(f"'{unit_name}': неверные {field_name} (указано: {user_pts}, должно: {official_pts})")
            elif field == "stats":
                diff = get_stats_diff(user_value, official_value)
                if diff:
                    errors.append(f"'{unit_name}': неверные {field_name} ({diff})")
                else:
                    errors.append(f"'{unit_name}': {field_name} не совпадают")
            else:
                errors.append(f"'{unit_name}': {field_name} не совпадают с официальными данными")
    
    # Проверяем имя (должно точно совпадать)
    if user_unit.get("name") != official_unit.get("name"):
        errors.append(f"'{unit_name}': имя должно быть '{official_unit.get('name')}'")
    
    return errors


def compare_points(user_points, official_points) -> bool:
    """Сравнить очки только по значимым полям: cost, models, keyword"""
    if not user_points and not official_points:
        return True
    if not user_points or not official_points:
        return False
    if not isinstance(user_points, list) or not isinstance(official_points, list):
        return user_points == official_points

    def normalize(pts):
        return sorted(
            [{"cost": str(p.get("cost", "")), "models": str(p.get("models", "")), "keyword": p.get("keyword")} for p in pts],
            key=lambda x: (x["cost"], x["models"])
        )

    return normalize(user_points) == normalize(official_points)


def extract_points_info(points_data) -> str:
    """Извлечь информацию об очках для отображения"""
    if not points_data:
        return "не указано"
    
    if isinstance(points_data, list):
        parts = []
        for pt in points_data:
            if isinstance(pt, dict):
                cost = pt.get("cost", "?")
                models = pt.get("models", "?")
                parts.append(f"{models} моделей = {cost} pts")
        return ", ".join(parts) if parts else "не указано"
    
    return str(points_data)


def get_stats_diff(user_stats, official_stats) -> str:
    """Получить разницу в характеристиках"""
    if not user_stats or not official_stats:
        return ""
    
    if not isinstance(user_stats, list) or not isinstance(official_stats, list):
        return ""
    
    if len(user_stats) == 0 or len(official_stats) == 0:
        return ""
    
    user_stat = user_stats[0] if user_stats else {}
    official_stat = official_stats[0] if official_stats else {}
    
    diffs = []
    stat_fields = ["m", "t", "sv", "w", "ld", "oc"]
    stat_names = {"m": "M", "t": "T", "sv": "Sv", "w": "W", "ld": "Ld", "oc": "OC"}
    
    for field in stat_fields:
        user_val = user_stat.get(field)
        official_val = official_stat.get(field)
        if user_val != official_val:
            diffs.append(f"{stat_names.get(field, field)}: {user_val} → {official_val}")
    
    return ", ".join(diffs)


def update_army_list_from_datasources(json_data) -> Tuple[dict, List[str]]:
    """
    Обновить список армии данными из datasources.
    Возвращает обновленный dict и список изменений.
    Принимает str или dict.
    """
    changes = []
    
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            return json_data, ["Ошибка парсинга JSON"]
    else:
        data = json_data.copy()  # Копируем чтобы не мутировать оригинал
    
    if "data" not in data or len(data["data"]) == 0:
        return data, ["Нет данных для обновления"]
    
    roster = data["data"][0]
    datasheets = roster.get("datasheets", [])
    
    if not datasheets:
        return data, ["Список пуст"]
    
    # Определяем фракцию
    faction = None
    for unit in datasheets:
        factions = unit.get("factions", [])
        if factions:
            faction = factions[0]
            break
    
    if not faction:
        return data, ["Не удалось определить фракцию"]
    
    # Загружаем данные фракции
    faction_file = find_faction_file(faction)
    if not faction_file:
        display_faction = get_display_faction_name(faction_file) if faction_file else faction
        return data, [f"Фракция '{display_faction}' не найдена в datasources"]
    
    display_faction = get_display_faction_name(faction_file)
    faction_data = load_faction_data(faction_file)
    if not faction_data:
        return data, [f"Не удалось загрузить данные фракции '{display_faction}'"]
    
    official_units = get_faction_units(faction_data)
    
    # Обновляем каждый юнит
    updated_datasheets = []
    
    for unit in datasheets:
        unit_name = unit.get("name", "").strip()
        unit_name_lower = unit_name.lower()
        
        # Ищем официальные данные юнита
        official_unit = None
        
        if unit_name_lower in official_units:
            official_unit = official_units[unit_name_lower]
        else:
            # Пробуем частичное совпадение
            for official_name, official_data in official_units.items():
                if unit_name_lower in official_name or official_name in unit_name_lower:
                    official_unit = official_data
                    break
        
        if official_unit:
            # Сохраняем пользовательские данные (количество моделей, выбор опций)
            user_unit_size = unit.get("unitSize", {})
            
            # Копируем официальные данные
            updated_unit = official_unit.copy()
            
            # Восстанавливаем пользовательские настройки
            if user_unit_size:
                updated_unit["unitSize"] = user_unit_size
            
            # Сохраняем faction_id из оригинала
            if "faction_id" in unit:
                updated_unit["faction_id"] = unit["faction_id"]
            
            # Проверяем изменения в очках
            old_points = unit.get("points", [])
            new_points = official_unit.get("points", [])
            
            if old_points != new_points:
                changes.append(f"📊 {unit_name}: обновлены очки")
            
            # Проверяем изменения в характеристиках
            old_stats = unit.get("stats", [])
            new_stats = official_unit.get("stats", [])
            
            if old_stats != new_stats:
                changes.append(f"📈 {unit_name}: обновлены характеристики")
            
            # Проверяем изменения в оружии
            old_ranged = unit.get("rangedWeapons", [])
            new_ranged = official_unit.get("rangedWeapons", [])
            
            if old_ranged != new_ranged:
                changes.append(f"🔫 {unit_name}: обновлено стрелковое оружие")
            
            old_melee = unit.get("meleeWeapons", [])
            new_melee = official_unit.get("meleeWeapons", [])
            
            if old_melee != new_melee:
                changes.append(f"⚔️ {unit_name}: обновлено рукопашное оружие")
            
            updated_datasheets.append(updated_unit)
        else:
            # Юнит не найден - оставляем как есть
            updated_datasheets.append(unit)
            changes.append(f"⚠️ {unit_name}: не найден в datasources")
    
    # Обновляем датащиты в roster
    roster["datasheets"] = updated_datasheets
    data["data"][0] = roster
    
    if not changes:
        changes.append("✅ Изменений не обнаружено")
    
    return data, changes
