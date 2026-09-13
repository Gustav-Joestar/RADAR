import os
import re
import time
import json
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests
from bs4 import BeautifulSoup
from logger import log
import database

MONTHS = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'июн': 6,
    'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
}

CATEGORY_MAP = {
    "movies": [1, 5, 7],     # 1=Зарубежные фильмы, 5=Наши фильмы, 7=Мультипликация
    "series": [4, 6, 16],    # 4=Зарубежные сериалы, 6=Телевизор, 16=Наши сериалы
    "anime": [10],           # 10=Аниме
    "games": [8],            # 8=Игры
    "software": [9]          # 9=Софт (категория 12 - научно-популярные фильмы исключена)
}


CATEGORY_HUBS = {
    "movies": ["http://rutor.info/kino", "http://rutor.info/nashe_kino"],
    "series": ["http://rutor.info/seriali", "http://rutor.info/tv"],
    "anime": ["http://rutor.info/anime"],
    "games": ["http://rutor.info/games"],
    "software": ["http://rutor.info/soft"]
}

STREAMING_PLATFORMS = [
    ("netflix", "Netflix"), ("hbo", "HBO Max"), ("apple tv", "Apple TV+"),
    ("amazon", "Amazon Prime"), ("disney", "Disney+"), ("кинопоиск", "Кинопоиск"),
    ("start", "START"), ("premier", "PREMIER"), ("okko", "Okko"),
    ("иви", "Иви"), ("ivi", "Иви"), ("kion", "KION"), ("bbc", "BBC"),
    ("hulu", "Hulu"), ("paramount", "Paramount+"), ("amc", "AMC"),
    ("showtime", "Showtime"), ("wink", "Wink")
]

VOICE_STUDIOS_SERIES = [
    ("lostfilm", "LostFilm"), ("кубик в кубе", "Кубик в кубе"),
    ("hdrezka", "HDRezka Studio"), ("newstudio", "NewStudio"),
    ("tvshows", "TVShows"), ("alexfilm", "AlexFilm"),
    ("пифагор", "Пифагор"), ("дубликат", "Дубликат"),
    ("coldfilm", "ColdFilm"), ("дубляж", "Дубляж"),
    ("red head sound", "Red Head Sound"), ("rhs", "Red Head Sound")
]

VOICE_STUDIOS_ANIME = [
    ("anilibria", "AniLibria"), ("studio band", "Studio Band"),
    ("anidub", "AniDUB"), ("shiza project", "SHIZA Project"),
    ("dream cast", "Dream Cast"), ("kansai", "Kansai Studio"),
    ("persona99", "Persona99"), ("crunchyroll", "Crunchyroll"),
    ("reanimedia", "Reanimedia"), ("jam club", "JAM Club"),
    ("jam", "JAM Club"), ("amber", "Amber"), ("steponee", "StepOnee")
]

GAME_REPACKERS = [
    ("fitgirl", "FitGirl"), ("dodi", "DODI"), ("decepticon", "Decepticon"),
    ("choo-choo", "Choo-Choo"), ("xatab", "xatab"), ("elamigos", "ElAmigos"),
    ("gog", "GOG"), ("pioneer", "Pioneer"), ("canek77", "Canek77"),
    ("dixen18", "Dixen18"), ("selezen", "SeleZen"), ("wose", "Wose")
]

SOFT_REPACKERS = [
    ("kprojluk", "KpoJluk"), ("кролик", "KpoJluk"),
    ("m0nkrus", "m0nkrus"), ("монкрус", "m0nkrus"),
    ("elchupacabra", "elchupacabra"), ("чупакабра", "elchupacabra"),
    ("d!akov", "D!akov"), ("дьяков", "D!akov"),
    ("tryroom", "TryRooM"), ("sanmini", "SanMini"),
    ("beloff", "Beloff"), ("centr", "Centr")
]

def is_bad_poster(url):
    """Check if poster URL is empty, broken, low-res thumbnail, or rating badge."""
    if not url or not isinstance(url, str):
        return True
    u = url.lower().strip()
    if not u.startswith(('http://', 'https://')):
        return True
    if any(bad in u for bad in [
        'radikal', 'rating', 's.rutor.info', 'imdb/pic', '.gif',
        'thumb', 'preview', '/t/', 'arrowup', 'arrowdown', 'smilies',
        'share', 'button', 'banner', 'logo', 'icon', 'ecx.images-amazon.com',
        'cdnbunny.org', 'kinopoisk.ru/rating', 'flag', 'rus_flag', 'flag_'
    ]):
        return True
    if '/thumb/' in u or '/preview/' in u:
        return True
    return False

def fetch_web_poster(title_ru, year=0, original_title="", category="movies"):
    if not title_ru or not title_ru.strip():
        return ""
    q_parts = [title_ru.strip()]
    if original_title and original_title.lower() != title_ru.lower():
        q_parts.append(original_title.strip())
    if year and int(year) > 0:
        q_parts.append(str(year))

    aspect_filter = "+filterui:aspect-tall"
    if category == "anime":
        q_parts.append("аниме постер")
    elif category == "games":
        q_parts.append("game cover box art")
    elif category == "software":
        q_parts.append("icon logo software")
        aspect_filter = "+filterui:aspect-square"
    elif category == "series":
        q_parts.append("постер сериал")
    else:
        q_parts.append("постер фильм")

    query = " ".join(q_parts)
    q_enc = urllib.parse.quote(query)
    url = f"https://www.bing.com/images/search?q={q_enc}&qft={aspect_filter}&form=IRFLTR"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        r = requests.get(url, headers=headers, impersonate='chrome124', timeout=6)
        html = r.text
        murls = re.findall(r'murl\u0026quot;:\u0026quot;(https?://[^\u0026]+)\u0026quot;', html)
        if not murls:
            murls = re.findall(r'"murl":"(https?://[^"]+)"', html)

        # Priority 1: Official high quality media sites
        priority_domains = [
            'avatars.mds.yandex.net', 'kinopoisk', 'kinorium', 'shikimori', 'myanimelist',
            'steamstatic', 'steamrip', 'gog.com', 'igromania', 'stopgame', 'mobygames',
            'softportal', 'comss', 'kinonews', 'film.ru', 'kg-portal.ru', 'wikimedia.org', 'lostfilm'
        ]
        for domain in priority_domains:
            for u in murls:
                if domain in u.lower() and not any(bad in u.lower() for bad in ['logo', 'icon', 'trailer', 'avatar', 'shot', 'banner', 'still']):
                    return u

        # Priority 2: Any clean image URL with jpg/png/webp
        for u in murls:
            u_clean = u.split('?')[0].lower()
            if any(u_clean.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
                if not any(bad in u.lower() for bad in ['banner', 'avatar', 'screenshot']):
                    return u

        # Size‑filtered fallback: choose first candidate whose height ≤ 480 px
        for candidate in murls:
            try:
                rr = requests.get(candidate, headers=headers, impersonate='chrome124', timeout=6)
                if rr.status_code != 200:
                    continue
                from io import BytesIO
                from PIL import Image
                img = Image.open(BytesIO(rr.content))
                if img.height <= 480:
                    return candidate
            except Exception:
                continue

        if murls:
            return murls[0]
    except Exception as e:
        log(f"⚠️ Ошибка поиска веб-постера для «{title_ru}»: {e}", "DEBUG")
    return ""

def is_valid_image_bytes(data):
    """Check if byte buffer has valid image magic bytes (JPEG, PNG, WEBP, GIF)."""
    if not data or len(data) < 512:
        return False
    if data.startswith(b'\xff\xd8\xff'):
        return True
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    if data.startswith(b'RIFF') and b'WEBP' in data[:16]:
        return True
    if data.startswith(b'GIF8'):
        return True
    return False

def download_image_bytes(poster_url):
    """Download image, unwrapping anti-hotlinking viewer pages (FastPic etc.) into direct signed image bytes."""
    if not poster_url or not poster_url.startswith(('http://', 'https://')):
        return None

    ref = "https://fastpic.org/" if "fastpic" in poster_url else "http://rutor.info/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": ref
    }

    try:
        r = requests.get(poster_url, headers=headers, impersonate="chrome124", timeout=8)
        if r.status_code == 200:
            if is_valid_image_bytes(r.content):
                return r.content

            # FastPic or image host returned an HTML landing/viewer page instead of direct image
            if b'<html' in r.content[:300].lower() or b'<!doctype' in r.content[:300].lower():
                soup = BeautifulSoup(r.text, 'html.parser')
                signed_candidates = []
                for im in soup.select('img'):
                    src = im.get('src', '')
                    if not src:
                        continue
                    if src.startswith('//'):
                        src = 'https:' + src
                    # FastPic signed image contains ?md5=
                    if '?md5=' in src or im.get('id') == 'image':
                        signed_candidates.insert(0, src)
                    elif any(c in im.get('class', []) for c in ['image', 'img-fluid']) and src.startswith('http'):
                        signed_candidates.append(src)

                for cand_url in signed_candidates:
                    r2 = requests.get(cand_url, headers={"User-Agent": headers["User-Agent"], "Referer": "https://fastpic.org/"}, impersonate="chrome124", timeout=8)
                    if r2.status_code == 200 and is_valid_image_bytes(r2.content):
                        return r2.content

    except Exception as e:
        log(f"⚠️ Ошибка загрузки изображения {poster_url[:80]}: {e}", "DEBUG")

    return None

def cache_poster_locally(torrent_id, poster_url, min_size_bytes=15360):
    """Download remote poster and save to data/posters/<torrent_id>.jpg for complete offline autonomy."""
    if not poster_url or not torrent_id:
        return ""
    if poster_url.startswith("/posters/"):
        return poster_url

    local_filename = f"{torrent_id}.jpg"
    local_file_path = os.path.join(database.POSTERS_DIR, local_filename)

    # Check if already downloaded and is a VALID image with sufficient size
    if os.path.exists(local_file_path):
        try:
            sz = os.path.getsize(local_file_path)
            req_size = min_size_bytes if min_size_bytes > 0 else 15360
            if sz >= req_size:
                with open(local_file_path, "rb") as f:
                    head = f.read(64)
                if is_valid_image_bytes(head):
                    return f"/posters/{local_filename}"
            # If too small, invalid, or stub, remove it
            os.remove(local_file_path)
        except Exception:
            pass

    img_data = download_image_bytes(poster_url)
    if img_data:
        # Strict minimum size validation (reject icons, badges, flags, small banners)
        if min_size_bytes > 0 and len(img_data) < min_size_bytes:
            log(f"⚠️ [ПОСТЕР] #{torrent_id}: отклонён {poster_url[:60]}... (размер {round(len(img_data)/1024, 1)} KB < {round(min_size_bytes/1024, 1)} KB)", "DEBUG")
            return ""

        try:
            with open(local_file_path, "wb") as f:
                f.write(img_data)
            log(f"💾 [ОФЛАЙН-КЭШ] Обложка #{torrent_id} сохранена: /posters/{local_filename} ({round(len(img_data)/1024, 1)} KB)", "DEBUG")
            return f"/posters/{local_filename}"
        except Exception as e:
            log(f"⚠️ Ошибка записи файла обложки #{torrent_id}: {e}", "DEBUG")

    return ""

GENRE_KEYWORDS = {
    "Боевик": ["боевик", "action"],
    "Комедия": ["комедия", "comedy"],
    "Драма": ["драма", "drama"],
    "Фантастика": ["фантастика", "sci-fi", "научная фантастика"],
    "Триллер": ["триллер", "thriller"],
    "Детектив": ["детектив", "mystery", "crime"],
    "Ужасы": ["ужасы", "horror"],
    "Приключения": ["приключения", "adventure"],
    "Фэнтези": ["фэнтези", "fantasy"],
    "Мультфильм": ["мультфильм", "анимация", "animation"],
    "Документальный": ["документальный", "documentary"],
    "Криминал": ["криминал", "криминальный"],
    "Семейный": ["семейный", "family"]
}

def parse_date_to_timestamp(date_str):
    try:
        s = date_str.replace('\xa0', ' ').strip()
        m_dash = re.search(r'(\d{2})-(\d{2})-(\d{4})', s)
        if m_dash:
            day, month, year = int(m_dash.group(1)), int(m_dash.group(2)), int(m_dash.group(3))
            return int(datetime(year, month, day, 12, 0, 0).timestamp())

        parts = s.split()
        if len(parts) >= 3:
            day = int(parts[0])
            month_str = parts[1].lower()[:3]
            month = MONTHS.get(month_str, 9)
            year_short = int(parts[2])
            year = 2000 + year_short if year_short < 100 else year_short
            dt = datetime(year, month, day, 12, 0, 0)
            return int(dt.timestamp())
    except Exception:
        pass
    return int(time.time())

def parse_size_gb(size_str):
    try:
        s = size_str.replace('\xa0', ' ').strip().upper()
        m = re.search(r'([\d\.]+)\s*([GMK]?B)', s)
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            if 'MB' in unit:
                return round(val / 1024.0, 3)
            elif 'KB' in unit:
                return round(val / (1024.0 * 1024.0), 3)
            elif 'GB' in unit:
                return round(val, 2)
    except Exception:
        pass
    return 0.0

def extract_quality(title, video_info=""):
    v_str = (video_info or '') + ' ' + (title or '')
    
    # 1. Exact resolution match (e.g. 1920x804, 3840x2160, 1280x720)
    m_res = re.search(r'(\d{3,4})\s*[xх*]\s*(\d{3,4})', v_str, re.IGNORECASE)
    if m_res:
        dim1, dim2 = int(m_res.group(1)), int(m_res.group(2))
        width = max(dim1, dim2)
        height = min(dim1, dim2)
        if width >= 3800 or height >= 2000:
            return '4K'
        if width >= 1900 or height >= 800:
            return '1080p'
        if width >= 1200 or height >= 500:
            return '720p'
        if width >= 600 or height >= 300:
            return 'SD'

    # 2. Strict word boundary check (explicitly ignore elektri4ka so 4k is not falsely triggered)
    t_clean = re.sub(r'elektri4ka|exkinoray|baibako|coldfilm', '', title, flags=re.IGNORECASE)
    if re.search(r'\b(?:2160p|4k|uhd)\b', t_clean, re.IGNORECASE):
        return '4K'
    if re.search(r'\b(?:1080p|1080i)\b', t_clean, re.IGNORECASE):
        return '1080p'
    if re.search(r'\b(?:720p)\b', t_clean, re.IGNORECASE):
        return '720p'
    if 'bdrip' in t_clean.lower():
        return '1080p' if '1080' in t_clean else 'BDRip'
    if 'web-dl' in t_clean.lower() or 'web-dlrip' in t_clean.lower():
        return '1080p'
    return '1080p'

KNOWN_COUNTRIES = [
    ("россия", "Россия"), ("ссср", "СССР"), ("рф", "Россия"),
    ("сша", "США"), ("usa", "США"),
    ("великобритания", "Великобритания"), ("британия", "Великобритания"), ("англия", "Великобритания"),
    ("франция", "Франция"), ("германия", "Германия"), ("италия", "Италия"), ("испания", "Испания"),
    ("канада", "Канада"), ("австралия", "Австралия"), ("япония", "Япония"), ("китай", "Китай"),
    ("гонконг", "Гонконг"), ("тайвань", "Тайвань"), ("индия", "Индия"),
    ("корея южная", "Южная Корея"), ("южная корея", "Южная Корея"), ("корея", "Южная Корея"),
    ("бразилия", "Бразилия"), ("мексика", "Мексика"), ("аргентина", "Аргентина"),
    ("индонезия", "Индонезия"), ("нидерланды", "Нидерланды"), ("бельгия", "Бельгия"),
    ("швеция", "Швеция"), ("норвегия", "Норвегия"), ("дания", "Дания"), ("финляндия", "Финляндия"),
    ("польша", "Польша"), ("чехия", "Чехия"), ("венгрия", "Венгрия"), ("австрия", "Австрия"),
    ("швейцария", "Швейцария"), ("турция", "Турция"), ("ирландия", "Ирландия"), ("греция", "Греция"),
    ("таиланд", "Таиланд"), ("новая зеландия", "Новая Зеландия"), ("юар", "ЮАР"),
    ("исландия", "Исландия"), ("израиль", "Израиль"), ("румыния", "Румыния"),
    ("португалия", "Португалия"), ("чили", "Чили"), ("колумбия", "Колумбия"),
    ("перу", "Перу"), ("сербия", "Сербия"), ("хорватия", "Хорватия"),
    ("украина", "Украина"), ("беларусь", "Беларусь"), ("казахстан", "Казахстан"),
    ("грузия", "Грузия"), ("армения", "Армения"), ("болгария", "Болгария"),
    ("эстония", "Эстония"), ("литва", "Литва"), ("латвия", "Латвия"),
    ("египет", "Египет"), ("марокко", "Марокко"), ("иран", "Иран")
]

STUDIO_STOPWORDS = {
    "entertainment", "pictures", "studios", "studio", "films", "film",
    "productions", "production", "media", "cinema", "inc", "llc", "ltd",
    "corp", "corporation", "company", "bros", "television", "tv",
    "village", "roadshow", "castle", "rock", "warner", "universal", "paramount",
    "columbia", "disney", "marvel", "netflix", "hbo", "sony", "fox", "lionsgate",
    "mgm", "tri-star", "dreamworks", "orion", "miramax", "pixar", "lucasfilm"
}

def extract_clean_country(full_text):
    if not full_text:
        return ""

    field_patterns = [
        r'(?:Страна(?:\s*/\s*студия)?|Country)\s*:\s*([^\n\r]+)',
        r'(?:Производство)\s*:\s*([^\n\r]+)',
        r'(?:Выпущено)\s*:\s*([^\n\r]+)'
    ]

    candidates = []
    for pat in field_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            val = re.sub(r'\s+', ' ', val)
            candidates.append(val)

    # 1. Search for known canonical countries in candidate field lines
    for cand in candidates:
        cand_lower = cand.lower()
        matched = []
        for kw, canonical in KNOWN_COUNTRIES:
            pos = cand_lower.find(kw)
            if pos != -1:
                matched.append((pos, canonical))
        if matched:
            matched.sort(key=lambda x: x[0])
            return matched[0][1]

    # 2. Check if first token in candidate is a clean non-studio word
    for cand in candidates:
        first_token = re.split(r'[,/|;]+', cand)[0].strip()
        first_token_clean = re.sub(r'[^\w\s-]', '', first_token).strip()
        token_words = set(first_token_clean.lower().split())
        if first_token_clean and not token_words.intersection(STUDIO_STOPWORDS):
            if 2 < len(first_token_clean) < 30 and len(first_token_clean.split()) <= 3 and not any(ch.isdigit() for ch in first_token_clean):
                return first_token_clean.capitalize()

    # 3. Fallback: scan full text for country mention
    for kw, canonical in KNOWN_COUNTRIES:
        if re.search(r'\b(?:страна|производство)\s*:[^\n\r]*?\b' + re.escape(kw) + r'\b', full_text, re.IGNORECASE):
            return canonical

    return ""

def fix_existing_countries_in_db():
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, country, description, video_info FROM releases WHERE category = 'movies'")
        rows = c.fetchall()
        updated_count = 0
        for r in rows:
            rid = r['id']
            curr_country = (r['country'] or '').strip()
            desc = (r['description'] or '') + ' ' + (r['video_info'] or '')
            curr_lower = curr_country.lower()
            needs_fix = not curr_country or any(sw in curr_lower for sw in STUDIO_STOPWORDS) or len(curr_country.split()) > 3
            if needs_fix:
                cleaned = extract_clean_country(f"Страна: {curr_country}\n{desc}")
                # If cleaned is found and differs, update it; if it was an ugly sentence and no clean country found, reset to empty
                target = cleaned if cleaned else ("" if len(curr_country.split()) > 3 else curr_country)
                if target != curr_country:
                    c.execute("UPDATE releases SET country = ? WHERE id = ?", (target, rid))
                    updated_count += 1
        conn.commit()
        conn.close()
        if updated_count > 0:
            log(f"🧹 [СТРАНЫ] Исправлены названия стран для {updated_count} фильмов в базе", "SUCCESS")
    except Exception as e:
        log(f"⚠️ Ошибка авто-исправления стран: {e}", "WARNING")

def scan_category(category_name, year=2026, max_pages=1):
    year_label = f" (год: {year})" if year and year > 0 else ""
    log(f"Начало радарного сканирования категории [{category_name}]{year_label}...", "INFO")
    cat_ids = CATEGORY_MAP.get(category_name, [1])
    urls_to_scan = list(CATEGORY_HUBS.get(category_name, []))
    for cat_id in cat_ids:
        for p in range(max_pages):
            if year and year > 0 and category_name in ("movies", "series", "anime"):
                urls_to_scan.append(f"http://rutor.info/search/{p}/{cat_id}/0/0/{year}")
            else:
                urls_to_scan.append(f"http://rutor.info/browse/{p}/{cat_id}/0/0")

    return _process_tracker_urls(urls_to_scan, category_name, year)

def scan_next_tracker_page(category_name, year=2026):
    y_val = int(year) if str(year).isdigit() else 0
    cat_ids = CATEGORY_MAP.get(category_name, [1])
    page = database.get_crawl_page(category_name, y_val)
    year_label = f" (год: {y_val})" if y_val > 0 else " (все годы)"
    log(f"📡 [РАДАР] Запрос следующей страницы трекера (#{page}) [{category_name}]{year_label}...", "INFO")
    urls_to_scan = []
    for cat_id in cat_ids:
        if y_val > 0 and category_name in ("movies", "series", "anime"):
            urls_to_scan.append(f"http://rutor.info/search/{page}/{cat_id}/0/0/{y_val}")
        else:
            urls_to_scan.append(f"http://rutor.info/browse/{page}/{cat_id}/0/0")

    res = _process_tracker_urls(urls_to_scan, category_name, y_val)
    database.advance_crawl_page(category_name, y_val)
    return res

def search_tracker_by_query(query, category_name="movies"):
    if not query or not query.strip():
        return 0
    clean_q = query.strip()
    query_variants = [clean_q]
    q_e = clean_q.replace('ё', 'е').replace('Ё', 'е')
    q_yo = clean_q.replace('е', 'ё').replace('Е', 'Ё')
    if q_e not in query_variants:
        query_variants.append(q_e)
    if q_yo not in query_variants:
        query_variants.append(q_yo)

    cat_ids = CATEGORY_MAP.get(category_name, [1, 5, 7] if category_name == "movies" else [1])
    urls_to_scan = []
    for q_var in query_variants:
        encoded_q = urllib.parse.quote(q_var)
        for cat_id in cat_ids:
            u = f"http://rutor.info/search/0/{cat_id}/0/0/{encoded_q}"
            if u not in urls_to_scan:
                urls_to_scan.append(u)

    log(f"🔎 [ОНЛАЙН-ПОИСК] Запрос трекера по названию «{clean_q}» в [{category_name}] (вариантов: {len(query_variants)})...", "INFO")
    return _process_tracker_urls(urls_to_scan, category_name, 0)

def _process_tracker_urls(urls_to_scan, category_name, year):
    scanned_torrent_ids = []
    unique_titles_to_fetch = []
    seen_titles = set()

    for url in urls_to_scan:
        log(f"📡 [СКАНЕР] Проверка страницы: {url}", "DEBUG")
        try:
            r = requests.get(url, impersonate='chrome124', timeout=8)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
            rows = soup.select('div#index tr')
                
            for tr in rows:
                t_link = tr.select_one('a[href*="/torrent/"]')
                if not t_link:
                    continue
                
                href = t_link['href']
                t_id_match = re.search(r'/torrent/(\d+)', href)
                if not t_id_match:
                    continue
                torrent_id = t_id_match.group(1)
                # Skip pinned rules / announcements
                if int(torrent_id) < 500000:
                    continue

                raw_title = t_link.text.strip()

                # Strict category isolation
                row_links_str = " ".join([a.get('href', '') for a in tr.select('a')])
                t_lower = raw_title.lower()

                is_anime_row = '/anime' in row_links_str or '/browse/0/10' in row_links_str or '/search/0/10' in row_links_str
                is_game_row = any(g in row_links_str for g in ['/games', '/browse/0/8', '/search/0/8'])
                is_soft_row = any(s in row_links_str for s in ['/soft', '/browse/0/9', '/browse/0/12', '/search/0/9', '/search/0/12'])
                is_other_row = any(o in row_links_str for o in ['/books', '/audio', '/browse/0/2', '/browse/0/11', '/browse/0/13', '/browse/0/14'])
                has_game_cues = bool(re.search(r'\b(?:repack\s+от|repack\s+by|steam\s*rip|dlc\s*pack|gog\b|pc\s*\|\s*repack)\b', t_lower))
                has_soft_cues = bool(re.search(r'\b(?:portable\b|активац|repack\s*by\s*kprojluk|repack\s*by\s*m0nkrus|x64\s*\[\d{4})\b', t_lower))

                if category_name in ("movies", "series"):
                    if is_anime_row or is_game_row or is_soft_row or is_other_row or has_game_cues or has_soft_cues:
                        continue
                elif category_name == "anime":
                    if is_game_row or is_soft_row or is_other_row or has_game_cues or has_soft_cues:
                        continue
                elif category_name == "games":
                    if is_soft_row or is_other_row or is_anime_row:
                        continue
                elif category_name == "software":
                    if is_game_row or is_other_row or is_anime_row:
                        continue

                tds = tr.find_all('td')
                date_str = tds[0].text.strip() if len(tds) > 0 else ''
                date_ts = parse_date_to_timestamp(date_str)
                size_str = tds[-2].text.strip() if len(tds) > 2 else ''
                size_gb = parse_size_gb(size_str)
                
                s_tag = tr.select_one('span.green')
                p_tag = tr.select_one('span.red')
                seeds = int(re.sub(r'\D', '', s_tag.text)) if s_tag else 0
                peers = int(re.sub(r'\D', '', p_tag.text)) if p_tag else 0

                if seeds == 0 and peers == 0 and size_gb == 0:
                    continue

                title_ru = raw_title
                title_en = ""
                rel_year = year if (year and year > 0) else 0

                y_m = re.search(r'\((\d{4})\)', raw_title)
                if y_m:
                    rel_year = int(y_m.group(1))

                if '/' in raw_title:
                    parts = raw_title.split('/')
                    title_ru = parts[0].strip()
                    second = parts[1].strip()
                    title_en = second.split('(')[0].strip() if '(' in second else second.split('|')[0].strip()
                elif '(' in raw_title:
                    title_ru = raw_title.split('(')[0].strip()

                # Check if release was marked "Не буду смотреть" or "Буду смотреть" (strictly isolated per category)
                is_ign = database.is_ignored(torrent_id, title_ru, rel_year, category=category_name)
                is_watch = database.is_watchlist(torrent_id, title_ru, rel_year, category=category_name)
                initial_status = 'ignored' if is_ign else ('watchlist' if is_watch else 'new')

                # Check if release is already in persistent cache with full details
                cached = database.get_release_by_id(torrent_id)
                if cached and (cached.get("description") or cached.get("poster_url") or cached.get("kp_rating") or cached.get("imdb_rating") or cached.get("shikimori_rating") or cached.get("metacritic_critic")):
                    # ALREADY IN CACHE: update only live seed/peer/size stats
                    database.update_tracker_stats(torrent_id, seeds, peers, size_gb, size_str, date_str, date_ts)
                    scanned_torrent_ids.append(torrent_id)
                    continue

                quality = extract_quality(raw_title)

                detected_country = ""
                if "/5/" in url or "nashe_kino" in url or "/16/" in url:
                    detected_country = "Россия"
                elif not title_en and '/' not in raw_title and not re.search(r'[a-zA-Z]{3,}', raw_title):
                    detected_country = "Россия"
                elif any(cue in t_lower for cue in ["от exkinoray", "files-x", "сериал ссср", "мосфильм", "ленфильм"]):
                    detected_country = "Россия"

                # Auto-reclassify series mistakenly listed under animation or movies
                if category_name == "movies":
                    is_series_cue = bool(re.search(r'\b(?:сезон\s*\d+|\d+\s*сезон|\d+x\d+|s\d+(?:e\d+)?|серии?\s*\d+[\d\-]*|мультсериал|мини-сериал)\b', raw_title, re.I))
                    if is_series_cue:
                        category_name = "series"
                        init_genre = "Мультсериал" if any(w in t_lower for w in ["мульт", "анимац", "animation"]) else "Сериал"
                    else:
                        init_genre = "Мультфильм" if any(w in t_lower for w in ["мультфильм", "мультсериал"]) else "Фильм"
                elif category_name == "anime":
                    init_genre = "Аниме"
                elif category_name == "games":
                    init_genre = "Игры"
                elif category_name == "software":
                    init_genre = "Программы"
                elif category_name == "series":
                    init_genre = "Сериал"
                else:
                    init_genre = "Фильм"


                # Extract initial title tags
                voice_studio_init = ""
                streaming_init = ""
                repack_author_init = ""
                release_format_init = ""
                app_version_init = ""
                is_ongoing_init = 0
                episodes_rel_init = 0
                episodes_tot_init = 0
                anime_type_init = ""
                has_subs_init = 1 if any(s in t_lower for s in ["sub", "субтитр"]) else 0

                seasons_count_init = 0

                if category_name == "series":
                    for kw, plat in STREAMING_PLATFORMS:
                        if kw in t_lower:
                            streaming_init = plat
                            break
                    for kw, stud in VOICE_STUDIOS_SERIES:
                        if kw in t_lower:
                            voice_studio_init = stud
                            break
                    m_ep = re.search(r'\[(\d+)-(\d+)\s+из\s+(\d+)\]', raw_title, re.I)
                    if m_ep:
                        episodes_rel_init = int(m_ep.group(2))
                        episodes_tot_init = int(m_ep.group(3))
                        is_ongoing_init = 1 if episodes_rel_init < episodes_tot_init else 0
                    elif 'онгоинг' in t_lower:
                        is_ongoing_init = 1

                    m_multi_s = re.search(r'(?:\[|\()(\d{1,2})-(\d{1,2})\s*сезон', raw_title, re.I)
                    if m_multi_s:
                        seasons_count_init = int(m_multi_s.group(2))
                    else:
                        m_single_s = re.search(r'(?:\[|\()(?:сезон\s*(\d{1,2})|(\d{1,2})\s*сезон|\s*(\d{1,2})x|\s*S(\d{1,2}))', raw_title, re.I)
                        if m_single_s:
                            seasons_count_init = int(m_single_s.group(1) or m_single_s.group(2) or m_single_s.group(3) or m_single_s.group(4) or 1)
                        else:
                            seasons_count_init = 1

                elif category_name == "anime":
                    for kw, stud in VOICE_STUDIOS_ANIME:
                        if kw in t_lower:
                            voice_studio_init = stud
                            break
                    is_series_cue = bool(re.search(r'\[\s*\d+x|\b\d+\s*сезон|\bсерии?\s*\d+|\b\d+\s*из\s*\d+|s\d+e\d+|\[\d+-\d+\]', raw_title, re.I))
                    if is_series_cue:
                        anime_type_init = "ТВ-сериал"
                        m_multi_s = re.search(r'(?:\[|\()(\d{1,2})-(\d{1,2})\s*сезон', raw_title, re.I)
                        if m_multi_s:
                            seasons_count_init = int(m_multi_s.group(2))
                        else:
                            m_single_s = re.search(r'(?:\[|\()(?:сезон\s*(\d{1,2})|(\d{1,2})\s*сезон|\s*(\d{1,2})x|\s*S(\d{1,2}))', raw_title, re.I)
                            if m_single_s:
                                seasons_count_init = int(m_single_s.group(1) or m_single_s.group(2) or m_single_s.group(3) or m_single_s.group(4) or 1)
                            else:
                                seasons_count_init = 1
                    elif any(w in raw_title.lower() for w in ["фильм", "movie", "полнометраж"]):
                        anime_type_init = "Полнометражный фильм"
                        seasons_count_init = 0
                    else:
                        anime_type_init = "ТВ-сериал"
                        seasons_count_init = 1

                elif category_name == "games":
                    for kw, auth in GAME_REPACKERS:
                        if kw in t_lower:
                            repack_author_init = auth
                            break
                    if "repack" in t_lower:
                        release_format_init = "RePack"
                    elif "portable" in t_lower:
                        release_format_init = "Portable"
                    elif "steam-rip" in t_lower or "steamrip" in t_lower:
                        release_format_init = "Steam-Rip"
                    elif "gog" in t_lower:
                        release_format_init = "GOG"

                elif category_name == "software":
                    for kw, auth in SOFT_REPACKERS:
                        if kw in t_lower:
                            repack_author_init = auth
                            break
                    if "repack" in t_lower and "portable" in t_lower:
                        release_format_init = "RePack & Portable"
                    elif "repack" in t_lower:
                        release_format_init = "RePack"
                    elif "portable" in t_lower:
                        release_format_init = "Portable"
                    m_v = re.search(r'\b(?:v|версия)?\s*(\d+\.\d+(?:\.\d+)*)\b', raw_title, re.I)
                    if m_v:
                        app_version_init = m_v.group(1)

                item_data = {
                    "torrent_id": torrent_id,
                    "category": category_name,
                    "title": raw_title,
                    "title_ru": title_ru,
                    "title_en": title_en,
                    "year": rel_year,
                    "date_added": date_str,
                    "date_ts": date_ts,
                    "size_gb": size_gb,
                    "size_str": size_str,
                    "seeds": seeds,
                    "peers": peers,
                    "quality": quality,
                    "video_info": "",
                    "audio_info": "",
                    "audio_tracks": "[]",
                    "voiceover": voice_studio_init,
                    "subtitles": "Есть" if has_subs_init else "",
                    "genre": init_genre,
                    "director": "",
                    "actors": "",
                    "description": "",
                    "country": detected_country,
                    "duration": "",
                    "imdb_rating": 0.0,
                    "kp_rating": 0.0,
                    "poster_url": "",
                    "torrent_url": f"http://d.rutor.info/download/{torrent_id}",
                    "magnet_url": f"magnet:?xt=urn:btih:&dn={urllib.parse.quote(raw_title)}",
                    "source_url": f"http://rutor.info{href}",
                    "seasons_info": "[]",
                    "mediainfo": "",
                    "user_status": initial_status,
                    "episodes_released": episodes_rel_init,
                    "episodes_total": episodes_tot_init,
                    "seasons_count": seasons_count_init,
                    "streaming_platform": streaming_init,
                    "voice_studio": voice_studio_init,
                    "repack_author": repack_author_init,
                    "release_format": release_format_init,
                    "crack_status": "",
                    "app_version": app_version_init,
                    "screenshots_json": "[]",
                    "shikimori_rating": 0.0,
                    "mal_rating": 0.0,
                    "metacritic_critic": 0.0,
                    "metacritic_user": 0.0,
                    "opencritic_rating": 0.0,
                    "has_subtitles": has_subs_init,
                    "is_ongoing": is_ongoing_init,
                    "anime_type": anime_type_init,
                    "software_category": "",
                    "system_reqs": "",
                    "repack_features": "",
                    "steam_rating": "",
                    "developer": "",
                    "publisher": "",
                    "platform": "PC" if category_name == "games" else "",
                    "engine": "",
                    "release_date": ""
                }

                database.upsert_release(item_data)
                scanned_torrent_ids.append(torrent_id)

                title_key = f"{title_ru.lower()}_{rel_year}"
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    unique_titles_to_fetch.append(torrent_id)

        except Exception as e:
            log(f"⚠️ Ошибка парсинга {url}: {e}", "ERROR")

    cached_count = len(scanned_torrent_ids) - len(unique_titles_to_fetch)
    log(f"Категория [{category_name}]: {len(scanned_torrent_ids)} раздач найдено ({cached_count} из кэша, {len(unique_titles_to_fetch)} новых).", "INFO")
    
    # Live speed optimization: Do not block scanner by fetching full details for 35 items.
    # Details and screenshots will load on-demand when the user clicks a card.
    log(f"⚡ [РАДАР] Витрина [{category_name}] готова мгновенно ({len(scanned_torrent_ids)} найдено).", "SUCCESS")

    log(f"Категория [{category_name}] полностью актуализирована!", "SUCCESS")
    return len(scanned_torrent_ids)

STOP_METADATA_FIELDS = (
    r'Страна|Студия|Производство|Выпущено|Премьера|Мировая премьера|Премьера в РФ|'
    r'Возраст|Рейтинг MPAA|Бюджет|Сборы|Время|Продолжительность|Качество|Качество видео|'
    r'Формат|Видео|Видеокодек|Кодек|Аудио|Аудиокодек|Звук|Перевод|Озвучивание|Озвучка|'
    r'Субтитры|Режиссер|Режиссёр|В ролях|Актеры|Файл|Релиз|Технические|MediaInfo|'
    r'Скриншоты|Рип от|Внимание'
)

STOP_GAME_FIELDS = (
    r'Особенности игры|Особенности репака|Особенности RePack|Особенности RePack-а|'
    r'Включенные DLC|DLC|Дополнения|Инструкция по установке|Установка|Системные требования|'
    r'Скриншоты|Список изменений|Патч-ноут|Важно'
)

STOP_SOFTWARE_FIELDS = (
    r'Состав сборки|Состав пакета|Особенности RePack|Особенности сборки|Особенности версии|'
    r'Инструкция по установке|Процедура лечения|Лечение|Таблетка|Ключи командной строки|'
    r'Тихая установка|Системные требования|Скриншоты|Контрольные суммы|CRC32'
)

def clean_description(text, cat="movies"):
    """Trim description by stop words according to category."""
    if not text or not isinstance(text, str):
        return ""
    desc = text.strip()
    if cat == "games":
        parts = re.split(r'(?:\n|\r|\s{2,})(?:' + STOP_GAME_FIELDS + r')\s*:?', desc, flags=re.I)
        if parts:
            desc = parts[0].strip()
    elif cat == "software":
        parts = re.split(r'(?:\n|\r|\s{2,})(?:' + STOP_SOFTWARE_FIELDS + r')\s*:?', desc, flags=re.I)
        if parts:
            desc = parts[0].strip()
    elif cat == "anime":
        parts = re.split(rf'(?:\n|\r|\s{{2,}})(?:{STOP_METADATA_FIELDS})\s*:', desc, flags=re.IGNORECASE)
        if parts:
            desc = parts[0].strip()
        desc = re.sub(rf'\s*(?:{STOP_METADATA_FIELDS})\s*:[^\n\r]+', '', desc, flags=re.IGNORECASE).strip()
    else:
        parts = re.split(rf'(?:\n|\r|\s{{2,}})(?:{STOP_METADATA_FIELDS})\s*:', desc, flags=re.IGNORECASE)
        if parts:
            desc = parts[0].strip()
        desc = re.sub(rf'\s*(?:{STOP_METADATA_FIELDS})\s*:[^\n\r]+', '', desc, flags=re.IGNORECASE).strip()
    return desc



GENRES_DICTIONARY = [
    'боевик', 'комедия', 'триллер', 'драма', 'ужасы', 'фантастика', 'фэнтези',
    'детектив', 'криминал', 'мелодрама', 'приключения', 'мультфильм', 'аниме',
    'документальный', 'вестерн', 'биография', 'история', 'семейный', 'военный',
    'мюзикл', 'спорт'
]

def extract_kinopoisk_id(html):
    """Extract Kinopoisk film/series ID from HTML text (links, badges, XML tags)."""
    if not html:
        return None
    patterns = [
        r'rating\.kinopoisk\.ru/(\d+)\.gif',
        r'kinopoisk\.ru/rating/(\d+)\.gif',
        r'kinopoisk\.ru/(?:film/|level/1/film/|series/)(\d+)',
        r'kinopoisk\.ru/(?:film|series)/(\d+)',
        r'kinopoisk\.ru/[^\s"\'<>]*?[?&]id=(\d+)'
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m and len(m.group(1)) >= 2:
            return m.group(1)
    return None

RATINGS_SEARCH_CACHE = {}

def fetch_ratings_by_search(title_ru, title_en="", year=0):
    """Search Kinopoisk ID and XML ratings by title + year (fast, non-blocking)."""
    cache_key = (title_ru.lower().strip() if title_ru else "", year or 0)
    if cache_key in RATINGS_SEARCH_CACHE:
        return RATINGS_SEARCH_CACHE[cache_key]

    kp_rating = 0.0
    imdb_rating = 0.0
    kp_id = None

    queries = []
    if title_ru and year:
        queries.append(f"кинопоиск {title_ru} {year}")
    elif title_ru:
        queries.append(f"кинопоиск {title_ru}")
    if title_en and year and title_en.lower() != title_ru.lower():
        queries.append(f"kinopoisk {title_en} {year}")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for q in queries[:2]:
        try:
            url_bing = f"https://www.bing.com/search?q={urllib.parse.quote(q)}"
            r_bing = requests.get(url_bing, impersonate='chrome124', timeout=1.5, headers=headers)
            cand_id = extract_kinopoisk_id(r_bing.text)
            if cand_id:
                r_xml = requests.get(f"https://rating.kinopoisk.ru/{cand_id}.xml", timeout=1.5)
                if r_xml.status_code == 200:
                    km = re.search(r'<kp_rating[^>]*>([\d\.]+)</kp_rating>', r_xml.text)
                    im = re.search(r'<imdb_rating[^>]*>([\d\.]+)</imdb_rating>', r_xml.text)
                    if km and float(km.group(1)) > 0:
                        kp_rating = round(float(km.group(1)), 1)
                    if im and float(im.group(1)) > 0:
                        imdb_rating = round(float(im.group(1)), 1)
                    kp_id = cand_id
                    if kp_rating > 0 or imdb_rating > 0:
                        break
        except Exception:
            pass

        if kp_rating > 0 or imdb_rating > 0:
            break

    result = (kp_rating, imdb_rating, kp_id)
    # Always cache result (even if 0) so we never repeat slow lookups for the same movie
    RATINGS_SEARCH_CACHE[cache_key] = result
    return result

SHIKIMORI_CACHE = {}

def fetch_shikimori_rating(title_ru, title_en=""):
    """Fast lookup for anime rating on Shikimori API (scores mirror MyAnimeList)."""
    cache_key = (title_ru.lower().strip() if title_ru else "", title_en.lower().strip() if title_en else "")
    if cache_key in SHIKIMORI_CACHE:
        return SHIKIMORI_CACHE[cache_key]

    queries = []
    if title_en and len(title_en) >= 3:
        queries.append(title_en)
    if title_ru and len(title_ru) >= 3:
        queries.append(title_ru)

    headers = {
        "User-Agent": "RADAR-Anime/2.0 (Media Release Discovery)",
        "Accept": "application/json"
    }

    for q in queries:
        try:
            url = f"https://shikimori.one/api/animes?search={urllib.parse.quote(q)}&limit=1"
            r = requests.get(url, headers=headers, impersonate="chrome124", timeout=2.5)
            if r.status_code == 200:
                data = r.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    score = float(item.get("score") or 0.0)
                    if score > 0:
                        res = (round(score, 1), round(score, 1))
                        SHIKIMORI_CACHE[cache_key] = res
                        return res
        except Exception:
            pass

    SHIKIMORI_CACHE[cache_key] = (0.0, 0.0)
    return (0.0, 0.0)

def extract_game_ratings(full_text):
    """Parse Metacritic (critic/user) and OpenCritic ratings from torrent description."""
    mc_critic = 0.0
    mc_user = 0.0
    oc_rating = 0.0

    # Metacritic critic (e.g. Metacritic: 86/100, Metacritic: 85)
    m_mc = re.search(r'Metacritic[:\s*]+([0-9]{2,3})(?:\s*/\s*100)?', full_text, re.I)
    if m_mc:
        try:
            val = float(m_mc.group(1))
            if 0 < val <= 100:
                mc_critic = val
        except Exception:
            pass

    # Metacritic user (e.g. Metacritic user: 8.2/10, Пользовательский рейтинг: 8.4)
    m_user = re.search(r'(?:Metacritic\s*user|Пользовательский\s*рейтинг|User\s*score)[:\s*]+([0-9](?:\.[0-9])?)(?:\s*/\s*10)?', full_text, re.I)
    if m_user:
        try:
            val = float(m_user.group(1))
            if 0 < val <= 10:
                mc_user = val
        except Exception:
            pass

    # OpenCritic (e.g. OpenCritic: 88, OpenCritic: 84/100)
    m_oc = re.search(r'OpenCritic[:\s*]+([0-9]{2,3})(?:\s*/\s*100)?', full_text, re.I)
    if m_oc:
        try:
            val = float(m_oc.group(1))
            if 0 < val <= 100:
                oc_rating = val
        except Exception:
            pass

    return mc_critic, mc_user, oc_rating

def extract_screenshots_from_details(details_table, main_poster_url=""):
    """Extract strictly screenshot image URLs from torrent details table (min 10 KB, no junk icons)."""
    if not details_table:
        return []
    screens = []
    seen = set()
    if main_poster_url:
        seen.add(main_poster_url.lower().strip())

    for img in details_table.select('img'):
        src = img.get('src', '')
        if not src:
            continue
        if src.startswith('//'):
            src = 'https:' + src
        s_lower = src.lower().strip()
        if not s_lower.startswith(('http://', 'https://')):
            continue
        # Strictly filter out badges, icons, logos, counters, smilies, flags, userbars, magnets
        if any(bad in s_lower for bad in [
            'rating', 'kinopoisk.ru', 'imdb/pic', '.gif', 'arrowup', 'arrowdown',
            'smilies', 'flag', 'rus_flag', 'flag_', 'userbar', 'button', 'logo_mini',
            's.rutor.info', 'counter', 'banner', 'pixel', 'stat', 'icon',
            'magnet', 'download', 'torrent', 'vk.com', 'telegram', 't.me', 'arrow'
        ]):
            continue
        if s_lower in seen:
            continue
        seen.add(s_lower)

        # Quick size check: filter out images < 10 KB
        clean_url = src.strip()
        try:
            h = requests.head(clean_url, timeout=1.2, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
            cl = int(h.headers.get('Content-Length', 0))
            if cl > 0 and cl < 10240: # strictly >= 10 KB threshold
                continue
        except Exception:
            pass

        screens.append(clean_url)
        if len(screens) >= 16:  # Cap at 16 screenshots
            break
    return screens


def backfill_missing_ratings(limit=30):
    """Background worker that finds movies in DB with 0 ratings and looks them up."""
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT torrent_id, title_ru, title_en, year 
            FROM releases 
            WHERE category in ('movies', 'series') 
              AND kp_rating = 0.0 AND imdb_rating = 0.0
            ORDER BY date_ts DESC 
            LIMIT ?
        """, (limit,))
        missing = [dict(r) for r in c.fetchall()]
        conn.close()

        if not missing:
            return

        for item in missing:
            try:
                kp, imdb, kp_id = fetch_ratings_by_search(
                    item.get("title_ru"), item.get("title_en"), item.get("year")
                )
                if kp > 0 or imdb > 0:
                    conn2 = database.get_connection()
                    c2 = conn2.cursor()
                    c2.execute("""
                        UPDATE releases 
                        SET kp_rating = ?, imdb_rating = ? 
                        WHERE torrent_id = ?
                    """, (kp, imdb, item["torrent_id"]))
                    conn2.commit()
                    conn2.close()
                    log(f"⭐ [РЕЙТИНГИ] #{item['torrent_id']} «{item.get('title_ru')[:30]}»: КП {kp or '—'} / IMDb {imdb or '—'}", "SUCCESS")
                time.sleep(0.4)
            except Exception:
                pass
    except Exception as e:
        log(f"⚠️ Ошибка backfill_missing_ratings: {e}", "WARNING")

def parse_full_details(torrent_id):
    url = f"http://rutor.info/torrent/{torrent_id}"
    try:
        r = requests.get(url, impersonate='chrome124', timeout=10)
        if r.status_code != 200:
            return None

        html = r.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(html, 'html.parser')
        details_table = soup.select_one('table#details')
        if not details_table:
            return None

        magnet_a = details_table.select_one('a[href^="magnet:"]')
        magnet_url = magnet_a['href'] if magnet_a else ""

        # Collect poster candidates with right-aligned / right-floated priority
        poster_candidates = []
        for img in details_table.select('img'):
            src = img.get('src', '')
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src
            if is_bad_poster(src):
                continue

            style = (img.get('style') or '').lower().replace(' ', '')
            align = (img.get('align') or '').lower().strip()
            p_style = (img.parent.get('style') or '').lower().replace(' ', '') if img.parent else ''
            p_align = (img.parent.get('align') or '').lower().strip() if img.parent else ''

            is_right = 'float:right' in style or align == 'right' or 'float:right' in p_style or p_align == 'right'
            if is_right:
                poster_candidates.insert(0, src)
            else:
                poster_candidates.append(src)

        full_text = details_table.text

        def find_field(patterns):
            for pat in patterns:
                m = re.search(pat, full_text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r'\s+', ' ', val)
                    return val
            return ""

        genre = find_field([r'Жанр:\s*([^\n\r]+)', r'Genre:\s*([^\n\r]+)'])
        director = find_field([r'Режиссер:\s*([^\n\r]+)', r'Режиссёр:\s*([^\n\r]+)', r'Director:\s*([^\n\r]+)'])
        actors = find_field([r'В ролях:\s*([^\n\r]+)', r'Актеры:\s*([^\n\r]+)', r'Cast:\s*([^\n\r]+)'])
        country = extract_clean_country(full_text)
        duration = find_field([r'Продолжительность:\s*([^\n\r]+)', r'Время:\s*([^\n\r]+)'])

        # Fallback genre detection if not explicitly parsed
        if not genre:
            found_genres = []
            text_lower = full_text.lower()
            for g in GENRES_DICTIONARY:
                if re.search(rf'\b{g}\b', text_lower):
                    found_genres.append(g.capitalize())
            if found_genres:
                genre = ", ".join(found_genres[:3])

        # Universal Multi-Line Parser for Translations, Audio tracks, Subtitles, Video
        translation_lines = []
        audio_lines = []
        subtitle_lines = []
        video_lines = []

        for line in full_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            line_clean = re.sub(r'\s+', ' ', line_str)

            # 1. Translations: Перевод, Перевод 1, Перевод #01, Озвучка, Озвучивание, Дубляж, Аудиоперевод
            m_trans = re.match(r'^(?:Перевод(?:\s*\d+|\s*#\d+)?|Озвучка|Озвучивание|Дубляж|Аудиоперевод)\s*:\s*(.*)', line_clean, re.I)
            if m_trans:
                val = m_trans.group(1).strip()
                if val:
                    header = line_clean.split(':', 1)[0].strip()
                    formatted_val = f"{header}: {val}" if any(c.isdigit() for c in header) else val
                    if formatted_val not in translation_lines:
                        translation_lines.append(formatted_val)

            # 2. Audio tracks: Аудио, Аудио 1, Аудио #1, Звук 1, Audio
            m_aud = re.match(r'^(?:Аудио(?:\s*\d+|\s*#\d+)?|Звук(?:\s*\d+|\s*#\d+)?|Audio(?:\s*\d+|\s*#\d+)?)\s*:\s*(.*)', line_clean, re.I)
            if m_aud:
                val = m_aud.group(1).strip()
                if val:
                    header = line_clean.split(':', 1)[0].strip()
                    formatted_track = f"{header}: {val}" if any(c.isdigit() for c in header) else val
                    if formatted_track not in audio_lines:
                        audio_lines.append(formatted_track)

            # 3. Subtitles: Субтитры, Subtitles
            m_sub = re.match(r'^(?:Субтитры(?:\s*\d+|\s*#\d+)?|Subtitles?)\s*:\s*(.*)', line_clean, re.I)
            if m_sub:
                val = m_sub.group(1).strip()
                if val and val.lower() != 'нет':
                    if val not in subtitle_lines:
                        subtitle_lines.append(val)

            # 4. Video: Видео, Video
            m_vid = re.match(r'^(?:Видео|Video)\s*:\s*(.*)', line_clean, re.I)
            if m_vid:
                val = m_vid.group(1).strip()
                if val and val not in video_lines:
                    video_lines.append(val)

        # Assemble unified voiceover / translation string
        voiceover = "; ".join(translation_lines) if translation_lines else find_field([r'Перевод:\s*([^\n\r]+)', r'Озвучивание:\s*([^\n\r]+)', r'Аудиоперевод:\s*([^\n\r]+)'])

        # Assemble video info
        video_info = " | ".join(video_lines) if video_lines else find_field([r'Видео:\s*([^\n\r]+)', r'Video:\s*([^\n\r]+)'])

        # Assemble structured audio tracks
        audio_tracks = []
        if audio_lines:
            audio_tracks = audio_lines
        else:
            audio_info_fallback = find_field([r'Аудио:\s*([^\n\r]+)', r'Audio:\s*([^\n\r]+)'])
            if audio_info_fallback:
                parts = re.split(r'[\r\n]+|;\s*|\s*\|\s*', audio_info_fallback)
                audio_tracks = [p.strip() for p in parts if p.strip()]

        audio_info = "; ".join(audio_tracks) if audio_tracks else ""

        # Assemble structured subtitles
        subtitles_list = []
        if subtitle_lines:
            for s in subtitle_lines:
                for sub_item in re.split(r',\s*(?![^()]*\))|;\s*', s):
                    sub_item = sub_item.strip()
                    if sub_item and sub_item.lower() != 'нет' and sub_item not in subtitles_list:
                        subtitles_list.append(sub_item)
        else:
            subtitles_str_fallback = find_field([r'Субтитры:\s*([^\n\r]+)', r'Subtitles:\s*([^\n\r]+)'])
            if subtitles_str_fallback:
                for p in re.split(r',\s*(?![^()]*\))|;\s*', subtitles_str_fallback):
                    p = p.strip()
                    if p and p.lower() != 'нет':
                        subtitles_list.append(p)

        # Determine category early from DB
        existing = database.get_release_by_id(torrent_id)
        cat = existing.get("category", "movies") if existing else "movies"

        # Category-specific description extraction with strict stop-words
        if cat == "games":
            desc_m = re.search(r'Описание:\s*\n*(.*?)(?=\n\s*(?:' + STOP_GAME_FIELDS + r')\s*:?|\Z)', full_text, re.DOTALL | re.I)
            description = desc_m.group(1).strip() if desc_m else ""
            if description:
                parts = re.split(r'(?:\n|\r|\s{2,})(?:' + STOP_GAME_FIELDS + r')\s*:?', description, flags=re.I)
                if parts:
                    description = parts[0].strip()
        elif cat == "software":
            desc_m = re.search(r'Описание:\s*\n*(.*?)(?=\n\s*(?:' + STOP_SOFTWARE_FIELDS + r')\s*:?|\Z)', full_text, re.DOTALL | re.I)
            description = desc_m.group(1).strip() if desc_m else ""
            if description:
                parts = re.split(r'(?:\n|\r|\s{2,})(?:' + STOP_SOFTWARE_FIELDS + r')\s*:?', description, flags=re.I)
                if parts:
                    description = parts[0].strip()
        elif cat == "anime":
            desc_m = re.search(rf'(?:Описание|О фильме|Сюжет):\s*\n*(.*?)(?=\n\s*(?:{STOP_METADATA_FIELDS})\s*:|\Z)', full_text, re.DOTALL | re.I)
            description = desc_m.group(1).strip() if desc_m else ""
            if description:
                parts = re.split(rf'(?:\n|\r|\s{{2,}})(?:{STOP_METADATA_FIELDS})\s*:', description, flags=re.IGNORECASE)
                if parts:
                    description = parts[0].strip()
                description = re.sub(rf'\s*(?:{STOP_METADATA_FIELDS})\s*:[^\n\r]+', '', description, flags=re.IGNORECASE).strip()
        else:
            desc_m = re.search(rf'(?:О фильме|Описание сериала|Описание|Сюжет|О сериале):\s*\n*(.*?)(?=\n\s*(?:{STOP_METADATA_FIELDS})\s*:|\Z)', full_text, re.DOTALL | re.I)
            description = desc_m.group(1).strip() if desc_m else ""
            if description:
                parts = re.split(rf'(?:\n|\r|\s{{2,}})(?:{STOP_METADATA_FIELDS})\s*:', description, flags=re.IGNORECASE)
                if parts:
                    description = parts[0].strip()
                description = re.sub(rf'\s*(?:{STOP_METADATA_FIELDS})\s*:[^\n\r]+', '', description, flags=re.IGNORECASE).strip()


        # 1. Fetch ratings from Kinopoisk XML (ultra-fast 0.16s via rating.kinopoisk.ru)
        kp_rating = 0.0
        imdb_rating = 0.0
        kp_id = extract_kinopoisk_id(html)

        if kp_id:
            try:
                r_kp = requests.get(f'https://rating.kinopoisk.ru/{kp_id}.xml', timeout=2)
                if r_kp.status_code == 200:
                    km = re.search(r'<kp_rating[^>]*>([\d\.]+)</kp_rating>', r_kp.text)
                    im = re.search(r'<imdb_rating[^>]*>([\d\.]+)</imdb_rating>', r_kp.text)
                    if km and float(km.group(1)) > 0:
                        kp_rating = round(float(km.group(1)), 1)
                    if im and float(im.group(1)) > 0:
                        imdb_rating = round(float(im.group(1)), 1)
            except Exception:
                pass

        # Text fallback if ratings are still 0
        if imdb_rating == 0.0:
            for pat in [
                r'IMDb[:\s*]+([0-9](?:\.[0-9])?)\s*(?:/\s*10)?',
                r'IMDB\s*[:\-]?\s*([0-9]\.[0-9])',
                r'rating[:\s]+([0-9]\.[0-9])\s*(?:/\s*10)?\s*\(IMDb\)'
            ]:
                imdb_m = re.search(pat, full_text, re.IGNORECASE)
                if imdb_m:
                    try:
                        imdb_rating = round(float(imdb_m.group(1)), 1)
                        break
                    except Exception:
                        pass

        if kp_rating == 0.0:
            for pat in [
                r'(?:Кинопоиск|Kinopoisk|КП)[:\s*]+([0-9](?:\.[0-9])?)\s*(?:/\s*10)?',
                r'Кинопоиск\s*[:\-]?\s*([0-9]\.[0-9])'
            ]:
                kp_txt_m = re.search(pat, full_text, re.IGNORECASE)
                if kp_txt_m:
                    try:
                        kp_rating = round(float(kp_txt_m.group(1)), 1)
                        break
                    except Exception:
                        pass

        # Existing DB record for title/year info
        existing = database.get_release_by_id(torrent_id)
        raw_title = soup.select_one('h1').text if soup.select_one('h1') else ""
        title_clean = raw_title.split('/')[0].split('(')[0].strip()
        t_ru = existing.get("title_ru") if existing else title_clean
        t_en = existing.get("title_en") if existing else ""
        r_year = existing.get("year") if existing else 0

        # Fast search fallback only if both ratings are still 0
        if kp_rating == 0.0 and imdb_rating == 0.0:
            s_kp, s_imdb, s_kpid = fetch_ratings_by_search(t_ru, t_en, r_year)
            if s_kp > 0:
                kp_rating = s_kp
            if s_imdb > 0:
                imdb_rating = s_imdb
            if not kp_id and s_kpid:
                kp_id = s_kpid

        # Season links for series
        seasons_info = []
        if any(w in raw_title.lower() for w in ['сезон', 'серии', 's0']):
            for s_num in range(1, 6):
                seasons_info.append({
                    "season": f"Сезон {s_num}",
                    "search_query": f"{title_clean} Сезон {s_num}"
                })

        mediainfo = ""
        mi_m = re.search(r'(MediaInfo:?.*)', full_text, re.DOTALL | re.IGNORECASE)
        if mi_m:
            mediainfo = mi_m.group(1)[:2000].strip()

        # Exact 'Добавлен' date from details table
        date_added_full = ""
        date_ts_full = 0
        m_added = re.search(r'Добавлен\s*</td>\s*<td>\s*(\d{2}-\d{2}-\d{4}(?:\s+\d{2}:\d{2}:\d{2})?)', r.text)
        if m_added:
            date_added_full = m_added.group(1).split()[0]
            date_ts_full = parse_date_to_timestamp(m_added.group(1))

        if existing:
            update_data = dict(existing)
            cat = update_data.get("category", "movies") or "movies"

            # Re-evaluate quality accurately using video_info resolution
            accurate_quality = extract_quality(update_data.get("title", ""), video_info)

            final_poster = ""
            # Priority 1: Official HD Kinopoisk poster directly from CDN (guaranteed clean, official, no flags/ads)
            if kp_id and cat in ("movies", "series"):
                # 1. High-resolution film_big (typically 80-200 KB)
                kp_big_url = f"https://st.kp.yandex.net/images/film_big/{kp_id}.jpg"
                local_kp = cache_poster_locally(torrent_id, kp_big_url, min_size_bytes=30000)
                if local_kp and local_kp.startswith("/posters/"):
                    final_poster = local_kp
                else:
                    # 2. Medium-resolution iphone360 fallback
                    kp_iphone_url = f"https://st.kp.yandex.net/images/film_iphone/iphone360_{kp_id}.jpg"
                    local_kp = cache_poster_locally(torrent_id, kp_iphone_url, min_size_bytes=10000)
                    if local_kp and local_kp.startswith("/posters/"):
                        final_poster = local_kp

            # Priority 2: Rutor tracker candidates (strictly filtered: min 10 KB, no icons/flags)
            if not final_poster:
                for cand in poster_candidates:
                    local_poster = cache_poster_locally(torrent_id, cand, min_size_bytes=10240)
                    if local_poster and local_poster.startswith("/posters/"):
                        final_poster = local_poster
                        break

            # Priority 3: Targeted web search poster per category
            if not final_poster:
                web_p = fetch_web_poster(t_ru, r_year, t_en, category=cat)
                if web_p and not is_bad_poster(web_p):
                    local_web = cache_poster_locally(torrent_id, web_p)
                    if local_web and local_web.startswith("/posters/"):
                        final_poster = local_web

            # Screenshot extraction (URLs only, zero disk download)
            screenshots_list = extract_screenshots_from_details(details_table, final_poster)

            # Category-specific metadata extraction
            shikimori_score, mal_score = 0.0, 0.0
            mc_critic, mc_user, oc_rating = 0.0, 0.0, 0.0
            streaming_plat = update_data.get("streaming_platform", "") or ""
            voice_stud = update_data.get("voice_studio", "") or ""
            repack_auth = update_data.get("repack_author", "") or ""
            rel_format = update_data.get("release_format", "") or ""
            crack_stat = update_data.get("crack_status", "") or ""
            app_ver = update_data.get("app_version", "") or ""
            soft_cat = update_data.get("software_category", "") or ""
            sys_reqs = update_data.get("system_reqs", "") or ""
            repack_feats = update_data.get("repack_features", "") or ""
            anime_type_val = update_data.get("anime_type", "") or ""
            is_ong_val = update_data.get("is_ongoing", 0) or 0
            ep_rel_val = update_data.get("episodes_released", 0) or 0
            ep_tot_val = update_data.get("episodes_total", 0) or 0

            f_lower = (full_text + " " + (update_data.get("title") or "")).lower()

            if cat == "series":
                for kw, plat in STREAMING_PLATFORMS:
                    if kw in f_lower:
                        streaming_plat = plat
                        break
                for kw, stud in VOICE_STUDIOS_SERIES:
                    if kw in f_lower:
                        voice_stud = stud
                        break
                m_ep = re.search(r'\[(\d+)-(\d+)\s+из\s+(\d+)\]', raw_title, re.I)
                if m_ep:
                    ep_rel_val = int(m_ep.group(2))
                    ep_tot_val = int(m_ep.group(3))
                    is_ong_val = 1 if ep_rel_val < ep_tot_val else 0
                elif 'онгоинг' in f_lower:
                    is_ong_val = 1

            elif cat == "anime":
                for kw, stud in VOICE_STUDIOS_ANIME:
                    if kw in f_lower:
                        voice_stud = stud
                        break
                raw_t = update_data.get("title", "")
                is_series_cue = bool(re.search(r'\[\s*\d+x|\b\d+\s*сезон|\bсерии?\s*\d+|\b\d+\s*из\s*\d+|s\d+e\d+|\[\d+-\d+\]', raw_t, re.I))
                if is_series_cue:
                    anime_type_val = "ТВ-сериал"
                elif any(w in raw_t.lower() for w in ["фильм", "movie", "полнометраж"]):
                    anime_type_val = "Полнометражный фильм"
                else:
                    anime_type_val = "ТВ-сериал"
                shikimori_score, mal_score = fetch_shikimori_rating(t_ru, t_en)

            elif cat == "games":
                mc_critic, mc_user, oc_rating = extract_game_ratings(full_text)
                for kw, auth in GAME_REPACKERS:
                    if kw in f_lower:
                        repack_auth = auth
                        break
                if "repack" in f_lower:
                    rel_format = "RePack"
                elif "portable" in f_lower:
                    rel_format = "Portable"
                elif "steam-rip" in f_lower or "steamrip" in f_lower:
                    rel_format = "Steam-Rip"
                elif "gog" in f_lower:
                    rel_format = "GOG"

                m_crack = re.search(r'(?:Таблетка|Crack|Защита|Лекарство)\s*:\s*([^\n\r]+)', full_text, re.I)
                if m_crack:
                    crack_stat = m_crack.group(1).strip()

                g_rel_date = find_field([r'Дата выпуска:\s*([^\n\r]+)', r'Release date:\s*([^\n\r]+)'])
                g_dev = find_field([r'Разработчик:\s*([^\n\r]+)', r'Developer:\s*([^\n\r]+)'])
                g_pub = find_field([r'Издательство:\s*([^\n\r]+)', r'Publisher:\s*([^\n\r]+)'])
                g_plat = find_field([r'Платформа:\s*([^\n\r]+)', r'Platform:\s*([^\n\r]+)']) or "PC"
                g_eng = find_field([r'Движок:\s*([^\n\r]+)', r'Engine:\s*([^\n\r]+)'])
                g_steam = find_field([r'Пользовательские оценки в Steam:\s*([^\n\r]+)'])

                m_req = re.search(r'(?:Системные требования|System requirements):\s*\n*(.*?)(?=\n\s*(?:' + STOP_GAME_FIELDS + r'|Описание|Скриншоты)\s*:?|\Z)', full_text, re.DOTALL | re.I)
                if m_req:
                    sys_reqs = m_req.group(1).strip()[:1500]
                m_feats = re.search(r'(?:Особенности репака|Особенности RePack|Особенности релиза|Особенности игры):\s*\n*(.*?)(?=\n\s*(?:Системные|Скриншоты|Описание)\s*:?|\Z)', full_text, re.DOTALL | re.I)
                if m_feats:
                    repack_feats = m_feats.group(1).strip()[:1500]

            elif cat == "software":
                for kw, auth in SOFT_REPACKERS:
                    if kw in f_lower:
                        repack_auth = auth
                        break
                if "repack" in f_lower and "portable" in f_lower:
                    rel_format = "RePack & Portable"
                elif "repack" in f_lower:
                    rel_format = "RePack"
                elif "portable" in f_lower:
                    rel_format = "Portable"

                m_v = re.search(r'\b(?:v|версия)?\s*(\d+\.\d+(?:\.\d+)*)\b', raw_title, re.I)
                if m_v:
                    app_ver = m_v.group(1)

                m_req = re.search(r'(?:Системные требования|ОС|Операционная система):\s*([^\n\r]+)', full_text, re.I)
                if m_req:
                    sys_reqs = m_req.group(1).strip()

                if any(k in f_lower for k in ["антивирус", "защит", "security", "firewall"]):
                    soft_cat = "Безопасность"
                elif any(k in f_lower for k in ["график", "photoshop", "editor", "рисова", "paint", "cad", "corel"]):
                    soft_cat = "Графика"
                elif any(k in f_lower for k in ["офис", "office", "word", "pdf", "текст"]):
                    soft_cat = "Офис"
                elif any(k in f_lower for k in ["плеер", "player", "кодек", "codec", "audio", "video", "конвертер"]):
                    soft_cat = "Мультимедиа"
                elif any(k in f_lower for k in ["браузер", "browser", "торрент", "torrent", "vpn", "download"]):
                    soft_cat = "Интернет"
                else:
                    soft_cat = "Система"

            update_data.update({
                "quality": accurate_quality,
                "poster_url": final_poster or "",
                "magnet_url": magnet_url or update_data.get("magnet_url", ""),
                "genre": genre or update_data.get("genre", ""),
                "director": (g_dev if cat == "games" else director) or update_data.get("director", ""),
                "actors": (g_pub if cat == "games" else actors) or update_data.get("actors", ""),
                "description": description or update_data.get("description", ""),
                "country": country or update_data.get("country", ""),
                "duration": duration or update_data.get("duration", ""),
                "voiceover": voiceover or update_data.get("voiceover", ""),
                "video_info": video_info or update_data.get("video_info", ""),
                "audio_info": audio_info or update_data.get("audio_info", ""),
                "audio_tracks": json.dumps(audio_tracks, ensure_ascii=False),
                "subtitles": json.dumps(subtitles_list, ensure_ascii=False) if subtitles_list else subtitles_str_fallback,
                "imdb_rating": imdb_rating or update_data.get("imdb_rating", 0.0),
                "kp_rating": kp_rating or update_data.get("kp_rating", 0.0),
                "seasons_info": json.dumps(seasons_info, ensure_ascii=False),
                "mediainfo": mediainfo,
                "screenshots_json": json.dumps(screenshots_list, ensure_ascii=False),
                "shikimori_rating": shikimori_score or update_data.get("shikimori_rating", 0.0),
                "mal_rating": mal_score or update_data.get("mal_rating", 0.0),
                "metacritic_critic": mc_critic or update_data.get("metacritic_critic", 0.0),
                "metacritic_user": mc_user or update_data.get("metacritic_user", 0.0),
                "opencritic_rating": oc_rating or update_data.get("opencritic_rating", 0.0),
                "streaming_platform": streaming_plat,
                "voice_studio": voice_stud,
                "repack_author": repack_auth,
                "release_format": rel_format,
                "crack_status": crack_stat,
                "app_version": app_ver,
                "software_category": soft_cat,
                "system_reqs": sys_reqs,
                "repack_features": repack_feats,
                "steam_rating": (g_steam if cat == "games" else "") or update_data.get("steam_rating", ""),
                "developer": (g_dev if cat == "games" else "") or update_data.get("developer", ""),
                "publisher": (g_pub if cat == "games" else "") or update_data.get("publisher", ""),
                "platform": (g_plat if cat == "games" else "") or update_data.get("platform", ""),
                "engine": (g_eng if cat == "games" else "") or update_data.get("engine", ""),
                "release_date": (g_rel_date if cat == "games" else "") or update_data.get("release_date", ""),
                "anime_type": anime_type_val,
                "is_ongoing": is_ong_val,
                "episodes_released": ep_rel_val,
                "episodes_total": ep_tot_val,
                "seasons_count": max(len(seasons_info) if seasons_info else 0, update_data.get("seasons_count", 0)),
                "has_subtitles": 1 if (subtitles_list or subtitles_str_fallback) else 0,
                "date_added": date_added_full or update_data.get("date_added", ""),
                "date_ts": date_ts_full or update_data.get("date_ts", 0)
            })
            database.upsert_release(update_data)

            if cat == "anime":
                r_str = f"Shikimori: {shikimori_score or '—'}"
            elif cat == "games":
                r_str = f"MC: {mc_critic or '—'} / OC: {oc_rating or '—'}"
            elif cat == "software":
                r_str = f"Версия: {app_ver or '—'}"
            else:
                r_str = f"КП {kp_rating or '—'} / IMDb {imdb_rating or '—'}"

            log(f"🎬 [ДЕТАЛИ] #{torrent_id} «{update_data.get('title_ru')[:35]}» | {cat} | {accurate_quality} | {r_str} | Обложка: {'✅' if update_data.get('poster_url') else '❌'} | Кадры: {len(screenshots_list)}", "SUCCESS")
            return update_data

        return None
    except Exception as e:
        log(f"⚠️ Ошибка парсинга #{torrent_id}: {e}", "WARNING")
        return None

def enhance_existing_movie_posters(limit=100):
    """Scan movies in DB with missing or bad posters and upgrade them with clean web posters."""
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT torrent_id, title_ru, year, title_en, poster_url 
            FROM releases 
            WHERE category = 'movies'
            ORDER BY 
                CASE WHEN user_status = 'watchlist' THEN 0 ELSE 1 END,
                date_ts DESC
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()

        to_fix = []
        for r in rows:
            if is_bad_poster(r.get('poster_url')):
                to_fix.append(r)
            if len(to_fix) >= limit:
                break

        if not to_fix:
            return 0

        log(f"🎨 [ОБЛОЖКИ] Улучшение качества постеров для {len(to_fix)} фильмов...", "INFO")
        fixed_count = 0
        for item in to_fix:
            tid = item['torrent_id']
            t_ru = item.get('title_ru') or ''
            yr = item.get('year') or 0
            t_en = item.get('title_en') or ''
            new_poster = fetch_web_poster(t_ru, yr, t_en)
            if new_poster and not is_bad_poster(new_poster):
                local_p = cache_poster_locally(tid, new_poster)
                database.update_release_poster(tid, local_p or new_poster)
                fixed_count += 1
                log(f"✨ [ОБЛОЖКА] #{tid} «{t_ru}» обновлен постер: {local_p or new_poster[:60]}...", "DEBUG")

        if fixed_count > 0:
            log(f"✅ [ОБЛОЖКИ] Успешно обновлено постеров: {fixed_count}", "SUCCESS")
        return fixed_count
    except Exception as e:
        log(f"⚠️ Ошибка улучшения постеров: {e}", "WARNING")
        return 0

def download_missing_local_posters(limit=50):
    """Background task: download remote poster URLs into data/posters/ for 100% offline autonomy."""
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT torrent_id, poster_url FROM releases 
            WHERE poster_url LIKE 'http%'
            ORDER BY 
                CASE WHEN user_status = 'watchlist' THEN 0 ELSE 1 END,
                date_ts DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return

        log(f"💾 [ОФЛАЙН-АВТОНОМИЯ] Проверка локального кэша для {len(rows)} обложек...", "INFO")
        cached_count = 0
        for r in rows:
            tid, p_url = r['torrent_id'], r['poster_url']
            local_url = cache_poster_locally(tid, p_url)
            if local_url and local_url.startswith("/posters/"):
                database.update_release_poster(tid, local_url)
                cached_count += 1

        if cached_count > 0:
            log(f"✅ [ОФЛАЙН-АВТОНОМИЯ] Успешно сохранено локально {cached_count} обложек!", "SUCCESS")
    except Exception as e:
        log(f"⚠️ Ошибка локального сохранения обложек: {e}", "WARNING")

# New function to validate and repair local posters

def repair_local_posters(limit=0):
    """Validate cached poster files; if corrupted or too small, re-download via fetch_web_poster and update DB."""
    import os
    from PIL import Image
    repaired = 0
    try:
        posters_dir = database.POSTERS_DIR
        files = [f for f in os.listdir(posters_dir) if f.lower().endswith('.jpg')]
        if limit > 0:
            files = files[:limit]
        for fname in files:
            path = os.path.join(posters_dir, fname)
            # Quick size check (ignore files <5KB)
            if os.path.getsize(path) < 5 * 1024:
                bad = True
            else:
                try:
                    Image.open(path).verify()
                    bad = False
                except Exception:
                    bad = True
            if bad:
                torrent_id = os.path.splitext(fname)[0]
                # Retrieve metadata from DB
                conn = database.get_connection()
                c = conn.cursor()
                c.execute("SELECT title_ru, year, title_en FROM releases WHERE torrent_id = ?", (torrent_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    new_url = fetch_web_poster(row['title_ru'], row['year'] or 0, row['title_en'] or '')
                    if new_url:
                        local = cache_poster_locally(torrent_id, new_url)
                        if local:
                            database.update_release_poster(torrent_id, local)
                            repaired += 1
                            log(f"🔧 [ОБЛОЖКА] Восстановлен постер для #{torrent_id}: {local}", "DEBUG")
                # Remove the bad file
                try:
                    os.remove(path)
                except Exception:
                    pass
        if repaired:
            log(f"✅ [ОБЛОЖКА] Восстановлено {repaired} постеров.", "SUCCESS")
    except Exception as e:
        log(f"⚠️ Ошибка восстановления постеров: {e}", "WARNING")
