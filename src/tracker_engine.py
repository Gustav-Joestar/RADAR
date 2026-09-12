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
    "movies": [1, 5],     # Зарубежные фильмы, Наши фильмы
    "series": [4, 16],    # Зарубежные сериалы, Наши сериалы
    "anime": [10, 7],     # Аниме, Мультипликация
    "games": [8],         # Игры
    "software": [9]       # Программы
}

CATEGORY_HUBS = {
    "movies": ["http://rutor.info/kino", "http://rutor.info/nashe_kino"],
    "series": ["http://rutor.info/seriali", "http://rutor.info/tv"],
    "anime": ["http://rutor.info/anime"],
    "games": ["http://rutor.info/games"],
    "software": ["http://rutor.info/soft"]
}

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

def detect_genre_from_title(title):
    t_low = title.lower()
    found = []
    for g_name, kws in GENRE_KEYWORDS.items():
        if any(kw in t_low for kw in kws):
            found.append(g_name)
    return ", ".join(found) if found else ""

def scan_category(category_name, year=2026, max_pages=2):
    year_label = f" (год: {year})" if year and year > 0 else ""
    log(f"Начало радарного сканирования категории [{category_name}]{year_label}...", "INFO")
    cat_ids = CATEGORY_MAP.get(category_name, [1])
    scanned_torrent_ids = []
    unique_titles_to_fetch = []
    seen_titles = set()

    # Build target URLs: Hubs (kino, nashe_kino) + year search pages
    urls_to_scan = list(CATEGORY_HUBS.get(category_name, []))
    for cat_id in cat_ids:
        for page in range(max_pages):
            if year and year > 0 and category_name in ("movies", "series", "anime"):
                urls_to_scan.append(f"http://rutor.info/search/{page}/{cat_id}/0/0/{year}")
            else:
                urls_to_scan.append(f"http://rutor.info/browse/{page}/{cat_id}/0/0")

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

                # Check if release is already in persistent cache with full details
                cached = database.get_release_by_id(torrent_id)
                if cached and (cached.get("description") or cached.get("poster_url") or cached.get("kp_rating") or cached.get("imdb_rating")):
                    # ALREADY IN CACHE: update only live seed/peer/size stats
                    database.update_tracker_stats(torrent_id, seeds, peers, size_gb, size_str, date_str, date_ts)
                    scanned_torrent_ids.append(torrent_id)
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

                quality = extract_quality(raw_title)
                initial_genre = detect_genre_from_title(raw_title)

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
                    "genre": initial_genre,
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
                    "mediainfo": ""
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
    log(f"Категория [{category_name}]: {len(scanned_torrent_ids)} раздач обработано ({cached_count} из кэша, {len(unique_titles_to_fetch)} новых).", "INFO")
    
    if unique_titles_to_fetch:
        log(f"Загрузка обложек и полных данных для {len(unique_titles_to_fetch)} новых тайтлов...", "INFO")
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(parse_full_details, unique_titles_to_fetch))

    log(f"Категория [{category_name}] полностью актуализирована!", "SUCCESS")

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
        for img in details_table.select('img'):
            src = img.get('src', '')
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src
            if any(k in src.lower() for k in ['fastpic', 'postimg', 'radikal', 'imageban', 'lostpix', 'ibn.im', 'firepic', 'media', 'poster', 'images', 'pictures', 'photobank', 'hostingkartinok', 'imgur', 'kinopoisk', 'kinomania', 'pic']):
                poster_url = src
                break
        if not poster_url:
            for img in details_table.select('img'):
                src = img.get('src', '')
                if not src:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                if not any(icon in src.lower() for icon in ['d.gif', 'm.png', 'com.gif', 'arrowup.gif', 'arrowdown.gif', 'smilies', 'share', 'button']):
                    poster_url = src
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
        country = find_field([r'Выпущено:\s*([^\n\r]+)', r'Страна:\s*([^\n\r]+)', r'Country:\s*([^\n\r]+)'])
        duration = find_field([r'Продолжительность:\s*([^\n\r]+)', r'Время:\s*([^\n\r]+)'])
        voiceover = find_field([r'Перевод:\s*([^\n\r]+)', r'Озвучивание:\s*([^\n\r]+)', r'Аудиоперевод:\s*([^\n\r]+)'])
        video_info = find_field([r'Видео:\s*([^\n\r]+)', r'Video:\s*([^\n\r]+)'])
        audio_info = find_field([r'Аудио:\s*([^\n\r]+)', r'Audio:\s*([^\n\r]+)'])
        subtitles_str = find_field([r'Субтитры:\s*([^\n\r]+)', r'Subtitles:\s*([^\n\r]+)'])

        desc_m = re.search(r'(?:О фильме|Описание|Сюжет|О сериале|О программе|Об игре):\s*\n*(.*?)(?=\n\s*(?:Выпущено|Продолжительность|Файл|Качество|Видео|Перевод|Релиз|Технические|MediaInfo|\Z))', full_text, re.DOTALL | re.IGNORECASE)
        description = desc_m.group(1).strip() if desc_m else ""

        audio_tracks = []
        if audio_info:
            parts = re.split(r'[\r\n]+|;\s*|\s*\|\s*', audio_info)
            for p in parts:
                p = p.strip()
                if p:
                    audio_tracks.append(p)

        subtitles_list = []
        if subtitles_str:
            parts = re.split(r'[\r\n]+|,\s*|;\s*', subtitles_str)
            for p in parts:
                p = p.strip()
                if p and p.lower() != 'нет':
                    subtitles_list.append(p)

        # 1. Fetch ratings from Kinopoisk and IMDb
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

            update_data.update({
                "quality": accurate_quality,
                "poster_url": poster_url or update_data.get("poster_url", ""),
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
                "subtitles": json.dumps(subtitles_list, ensure_ascii=False) if subtitles_list else subtitles_str,
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
