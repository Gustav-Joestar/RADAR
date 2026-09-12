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
    "anime": [10, 7],        # 10=Аниме, 7=Мультипликация
    "games": [8],            # 8=Игры
    "software": [9, 12]      # 9, 12=Программы
}

CATEGORY_HUBS = {
    "movies": ["http://rutor.info/kino", "http://rutor.info/nashe_kino"],
    "series": ["http://rutor.info/seriali", "http://rutor.info/tv"],
    "anime": ["http://rutor.info/anime"],
    "games": ["http://rutor.info/games"],
    "software": ["http://rutor.info/soft"]
}

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
        'cdnbunny.org', 'kinopoisk.ru/rating'
    ]):
        return True
    if '/thumb/' in u or '/preview/' in u:
        return True
    return False

def fetch_web_poster(title_ru, year=0, original_title=""):
    if not title_ru or not title_ru.strip():
        return ""
    q_parts = [title_ru.strip()]
    if original_title and original_title.lower() != title_ru.lower():
        q_parts.append(original_title.strip())
    if year and int(year) > 0:
        q_parts.append(str(year))
    q_parts.append("постер фильм")

    # Updated fetch_web_poster with height constraint (≤480px)
    query = " ".join(q_parts)
    q_enc = urllib.parse.quote(query)
    # Strictly vertical portrait aspect ratio filter
    url = f"https://www.bing.com/images/search?q={q_enc}&qft=+filterui:aspect-tall&form=IRFLTR"
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

        # Priority 1: High quality official cinema sites with official vertical art
        priority_domains = ['avatars.mds.yandex.net', 'kinopoisk', 'kinorium', 'kinonews', 'film.ru', 'kg-portal.ru', 'wikimedia.org', 'lostfilm']
        for domain in priority_domains:
            for u in murls:
                if domain in u.lower() and not any(bad in u.lower() for bad in ['logo', 'icon', 'trailer', 'avatar', 'shot', 'banner', 'still']):
                    return u

        # Priority 2: Any clean image URL with jpg/png/webp
        for u in murls:
            u_clean = u.split('?')[0].lower()
            if any(u_clean.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
                if not any(bad in u.lower() for bad in ['logo', 'icon', 'banner', 'avatar', 'screenshot']):
                    return u

        # Size‑filtered fallback: choose first candidate whose height ≤ 480 px
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

def cache_poster_locally(torrent_id, poster_url):
    """Download remote poster and save to data/posters/<torrent_id>.jpg for complete offline autonomy."""
    if not poster_url or not torrent_id:
        return ""
    if poster_url.startswith("/posters/"):
        return poster_url

    local_filename = f"{torrent_id}.jpg"
    local_file_path = os.path.join(database.POSTERS_DIR, local_filename)

    # If already downloaded and valid, return local URL
    if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 1024:
        return f"/posters/{local_filename}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.google.com/"
        }
        r = requests.get(poster_url, headers=headers, impersonate="chrome124", timeout=6)
        if r.status_code == 200 and len(r.content) > 1024:
            with open(local_file_path, "wb") as f:
                f.write(r.content)
            log(f"💾 [ОФЛАЙН-КЭШ] Обложка сохранена локально: /posters/{local_filename} ({round(len(r.content)/1024, 1)} KB)", "DEBUG")
            return f"/posters/{local_filename}"
    except Exception as e:
        log(f"⚠️ Не удалось локально сохранить постер #{torrent_id}: {e}", "DEBUG")

    return poster_url

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
        parts = date_str.replace('\xa0', ' ').strip().split()
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
    encoded_q = urllib.parse.quote(clean_q)
    cat_ids = CATEGORY_MAP.get(category_name, [1, 5, 7] if category_name == "movies" else [1])
    urls_to_scan = []
    for cat_id in cat_ids:
        urls_to_scan.append(f"http://rutor.info/search/0/{cat_id}/0/0/{encoded_q}")

    log(f"🔎 [ОНЛАЙН-ПОИСК] Запрос трекера по названию «{clean_q}» в [{category_name}]...", "INFO")
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

                # Check for category isolation to strictly prevent games, software, audio, books from leaking into movies/series
                row_links_str = " ".join([a.get('href', '') for a in tr.select('a')])
                is_game_row = any(g in row_links_str for g in ['/games', '/browse/0/8', '/search/0/8'])
                is_soft_row = any(s in row_links_str for s in ['/soft', '/browse/0/9', '/browse/0/12', '/search/0/9', '/search/0/12'])
                is_other_row = any(o in row_links_str for o in ['/books', '/audio', '/browse/0/2', '/browse/0/11', '/browse/0/13', '/browse/0/14'])
                t_lower = raw_title.lower()
                has_non_film_cues = bool(re.search(r'\b(?:repack(?:\s+by|\s+от)?|gog|steam\s*rip|dlc\s*pack|portable|комикс|аудиокнига|журнал|книга|mp3|flac)\b', t_lower))

                if category_name in ("movies", "series"):
                    if is_game_row or is_soft_row or is_other_row or has_non_film_cues:
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

                # Check if release was marked "Не буду смотреть" or "Буду смотреть"
                is_ign = database.is_ignored(torrent_id, title_ru, rel_year)
                is_watch = database.is_watchlist(torrent_id, title_ru, rel_year)
                initial_status = 'ignored' if is_ign else ('watchlist' if is_watch else 'new')

                # Check if release is already in persistent cache with full details
                cached = database.get_release_by_id(torrent_id)
                if cached and (cached.get("description") or cached.get("poster_url") or cached.get("kp_rating") or cached.get("imdb_rating")):
                    # ALREADY IN CACHE: update only live seed/peer/size stats
                    database.update_tracker_stats(torrent_id, seeds, peers, size_gb, size_str, date_str, date_ts)
                    scanned_torrent_ids.append(torrent_id)
                    continue

                quality = extract_quality(raw_title)

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
                    "voiceover": "",
                    "subtitles": "",
                    "genre": "",
                    "director": "",
                    "actors": "",
                    "description": "",
                    "country": "",
                    "duration": "",
                    "imdb_rating": 0.0,
                    "kp_rating": 0.0,
                    "poster_url": "",
                    "torrent_url": f"http://d.rutor.info/download/{torrent_id}",
                    "magnet_url": f"magnet:?xt=urn:btih:&dn={urllib.parse.quote(raw_title)}",
                    "source_url": f"http://rutor.info{href}",
                    "seasons_info": "[]",
                    "mediainfo": "",
                    "user_status": initial_status
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
    
    # Priority 1: Immediately fetch details and local posters for the top 15 releases of page 1
    page_1_data = database.query_releases(category=category_name, page=1, limit=15)
    page_1_needed = [it["torrent_id"] for it in page_1_data.get("items", []) if not it.get("poster_url") or not it.get("description")]
    
    if page_1_needed:
        log(f"⚡ [ПОСТЕРЫ] Мгновенная загрузка данных и обложек для первых {len(page_1_needed)} релизов витрины...", "INFO")
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(parse_full_details, page_1_needed))
        log(f"✅ [ПОСТЕРЫ] Витрина первой страницы полностью готова ({len(page_1_needed)} обложек)!", "SUCCESS")

    # Priority 2: Process remaining background releases lazily in background
    remaining_to_fetch = [tid for tid in unique_titles_to_fetch if tid not in page_1_needed]
    if remaining_to_fetch:
        import threading
        def _fetch_remaining_lazily(items):
            time.sleep(1.0)
            for tid in items:
                try:
                    parse_full_details(tid)
                    time.sleep(0.3)
                except Exception:
                    pass
        threading.Thread(target=_fetch_remaining_lazily, args=(remaining_to_fetch,), daemon=True).start()

    log(f"Категория [{category_name}] полностью актуализирована!", "SUCCESS")
    return len(scanned_torrent_ids)

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

        poster_url = ""
        # Choose poster from torrent detail page:
        # On Rutor, the official cover is always placed on the right (float:right or align="right")
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

            if 'float:right' in style or align == 'right' or 'float:right' in p_style or p_align == 'right':
                poster_url = src
                log(f"🖼️ [ПОСТЕР] #{torrent_id} найдена обложка справа (float:right): {poster_url[:80]}...", "DEBUG")
                break

        # Priority 2: first clean image in details_table
        if not poster_url:
            for img in details_table.select('img'):
                src = img.get('src', '')
                if not src:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                if is_bad_poster(src):
                    continue
                poster_url = src
                log(f"🖼️ [ПОСТЕР] #{torrent_id} взята первая подходящая картинка: {poster_url[:80]}...", "DEBUG")
                break

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

        desc_m = re.search(r'(?:О фильме|Описание|Сюжет|О сериале|О программе|Об игре):\s*\n*(.*?)(?=\n\s*(?:Выпущено|Продолжительность|Файл|Качество|Видео|Перевод|Релиз|Технические|MediaInfo|\Z))', full_text, re.DOTALL | re.IGNORECASE)
        description = desc_m.group(1).strip() if desc_m else ""

        # 1. Fetch ratings from Kinopoisk and IMDb, and use Kinopoisk poster as fallback
        kp_rating = 0.0
        imdb_rating = 0.0

        kp_m = re.search(r'kinopoisk\.ru/film/(\d+)', html)
        if kp_m:
            kp_id = kp_m.group(1)
            try:
                r_kp = requests.get(f'https://rating.kinopoisk.ru/{kp_id}.xml', timeout=4)
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
            imdb_m = re.search(r'IMDb[:\s*]+(\d+(?:\.\d+)?)\s*(?:/\s*10)?', full_text, re.IGNORECASE)
            if imdb_m:
                imdb_rating = round(float(imdb_m.group(1)), 1)
        if kp_rating == 0.0:
            kp_txt_m = re.search(r'(?:Кинопоиск|Kinopoisk|КП)[:\s*]+(\d+(?:\.\d+)?)\s*(?:/\s*10)?', full_text, re.IGNORECASE)
            if kp_txt_m:
                kp_rating = round(float(kp_txt_m.group(1)), 1)

        # Season links for series
        seasons_info = []
        raw_title = soup.select_one('h1').text if soup.select_one('h1') else ""
        title_clean = raw_title.split('/')[0].split('(')[0].strip()

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

        existing = database.get_release_by_id(torrent_id)
        if existing:
            update_data = dict(existing)
            # Re-evaluate quality accurately using video_info resolution
            accurate_quality = extract_quality(update_data.get("title", ""), video_info)

            # Use poster directly from torrent page without size checks
            final_poster = poster_url
            # Auto-cache poster locally for complete offline autonomy
            if final_poster and final_poster.startswith("http"):
                local_poster = cache_poster_locally(torrent_id, final_poster)
                if local_poster:
                    final_poster = local_poster

            update_data.update({
                "quality": accurate_quality,
                "poster_url": final_poster or "",
                "magnet_url": magnet_url or update_data.get("magnet_url", ""),
                "genre": genre or update_data.get("genre", ""),
                "director": director or update_data.get("director", ""),
                "actors": actors or update_data.get("actors", ""),
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
                "mediainfo": mediainfo
            })
            database.upsert_release(update_data)
            r_str = f"КП {kp_rating or '—'} / IMDb {imdb_rating or '—'}"
            log(f"🎬 [ДЕТАЛИ] #{torrent_id} «{update_data.get('title_ru')[:35]}» | {accurate_quality} | {r_str} | Обложка: {'✅' if update_data.get('poster_url') else '❌'}", "SUCCESS")
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
