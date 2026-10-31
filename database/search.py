import re
import unicodedata
from datetime import datetime, timedelta
from typing import List, Tuple
from difflib import SequenceMatcher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from database.session import AsyncSessionLocal
from models.message import CargoMessage

NOISE_WORDS = {
    'из', 'в', 'до', 'на', 'от', 'с', 'по', 'г', 'город', 'рф', 'руз', 'uz', 'ru', 'kz', 'by', 'cn', 'pl', 'tr',
    'погрузка', 'выгрузка', 'отправление', 'доставка', 'направление', 'маршрут',
    'груз', 'нужна', 'нужен', 'ищу', 'есть', 'тент', 'реф', 'изотерм', 'паровоз',
    'фура', 'машина', 'тонн', 'кг', 'тонны', 'шт', 'ставка', 'оплата', 'завтра', 'сегодня',
    'from', 'to', 'cargo', 'truck', 'ref', 'tent', 'qayerdan', 'qayerga', 'shahri', 'oblast', 'region'
}

TRANSLIT_CYR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'ў': 'u', 'ғ': 'g', 'қ': 'q', 'ҳ': 'h'
}

LAT_TO_CYR_MAP = {
    'sh': 'ш', 'ch': 'ч', 'zh': 'ж', 'shch': 'щ', 'ts': 'ц',
    'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'z': 'з',
    'i': 'и', 'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
    'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф', 'h': 'х',
    'q': 'қ', 'ў': 'у', 'ғ': 'г', 'ҳ': 'х'
}

def transliterate(text: str) -> str:
    text = text.lower()
    return "".join(TRANSLIT_CYR_TO_LAT.get(char, char) for char in text)

def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    for lat, cyr in sorted(LAT_TO_CYR_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(lat, cyr)
    return text

def is_similar(word1: str, word2: str, threshold: float = 0.72) -> bool:
    if word1 == word2:
        return True
    if len(word1) < 3 or len(word2) < 3:
        return False
    return SequenceMatcher(None, word1, word2).ratio() >= threshold

def clean_for_duplicate_check(text: str) -> str:
    """Глубокая очистка текста для отсечения дублей от того же логиста"""
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text).lower()
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()

def is_similar_duplicate_in_search(new_text: str, existing_texts: list, threshold: float = 0.85) -> bool:
    """Проверяет, является ли текст дубликатом уже добавленного в выдачу (похожесть >= 85%)"""
    clean_new = clean_for_duplicate_check(new_text)
    if len(clean_new) < 15:
        return False
        
    for old_txt in existing_texts:
        if abs(len(clean_new) - len(old_txt)) > 60:
            continue
        if SequenceMatcher(None, clean_new, old_txt).ratio() >= threshold:
            return True
    return False

def check_route_with_character_distance(text: str, origin_norm: str, dest_norm: str) -> bool:
    norm_full_text = normalize_text(text)
    
    words_map = []
    for match in re.finditer(r'[а-яa-zӯғқҳ]+', norm_full_text):
        w = match.group()
        if w not in NOISE_WORDS and len(w) > 1:
            words_map.append((w, match.start(), match.end()))

    if not words_map:
        return False

    origin_matches = []
    dest_matches = []

    for w, start, end in words_map:
        if is_similar(origin_norm, w) or is_similar(transliterate(origin_norm), w):
            origin_matches.append((start, end))
        if is_similar(dest_norm, w) or is_similar(transliterate(dest_norm), w):
            dest_matches.append((start, end))

    if not origin_matches or not dest_matches:
        return False

    # СТРОГОЕ НАПРАВЛЕНИЕ: Откуда должно идти РАНЬШЕ, чем Куда в пределах 15 символов
    for o_start, o_end in origin_matches:
        for d_start, d_end in dest_matches:
            if o_end <= d_start:
                char_distance = d_start - o_end
                if 0 <= char_distance <= 15:
                    return True

    return False


async def search_cargo_route_paginated(
    origin: str, 
    destination: str, 
    page: int = 1, 
    per_page: int = 10
) -> Tuple[List[CargoMessage], int]:
    if not origin or not destination:
        return [], 0

    origin_norm = normalize_text(origin)
    dest_norm = normalize_text(destination)

    origin_clean = re.sub(r'[^а-яa-zӯғқҳ]', '', origin_norm)
    dest_clean = re.sub(r'[^а-яa-zӯғқҳ]', '', dest_norm)

    if not origin_clean or not dest_clean:
        return [], 0

    orig_variants = {origin.lower(), origin_clean, transliterate(origin_clean)}
    dest_variants = {destination.lower(), dest_clean, transliterate(dest_clean)}

    async with AsyncSessionLocal() as session:
        time_limit = datetime.utcnow() - timedelta(hours=48)
        
        orig_conditions = [CargoMessage.text.ilike(f"%{v}%") for v in orig_variants if len(v) > 1]
        dest_conditions = [CargoMessage.text.ilike(f"%{v}%") for v in dest_variants if len(v) > 1]

        stmt = (
            select(CargoMessage)
            .where(
                and_(
                    CargoMessage.message_date >= time_limit,
                    or_(*orig_conditions),
                    or_(*dest_conditions)
                )
            )
            .order_by(CargoMessage.message_date.desc())
        )
        
        result = await session.execute(stmt)
        candidates = result.scalars().all()
        
        matched_messages = []
        seen_clean_texts = []
        
        for msg in candidates:
            if not msg.text:
                continue
            # Проверка направления и расстояния до 30 символов
            if check_route_with_character_distance(msg.text, origin_clean, dest_clean):
                # Защита от дубликатов в выдаче
                if is_similar_duplicate_in_search(msg.text, seen_clean_texts):
                    continue
                    
                seen_clean_texts.append(clean_for_duplicate_check(msg.text))
                matched_messages.append(msg)

        total_count = len(matched_messages)
        if total_count == 0:
            return [], 0

        offset = (page - 1) * per_page
        paginated_slice = matched_messages[offset:offset + per_page]
        
        return paginated_slice, total_count