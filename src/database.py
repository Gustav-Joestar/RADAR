import sqlite3
import os
import time
import re
import hashlib
import shutil
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
POSTERS_DIR = os.path.join(DATA_DIR, "posters")
TEMP_CACHE_DIR = os.path.join(DATA_DIR, "temp_cache")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(POSTERS_DIR, exist_ok=True)
os.makedirs(TEMP_CACHE_DIR, exist_ok=True)
RADAR_DB = os.path.join(DATA_DIR, "radar.db")

def get_session_cache(key: str):
    """Retrieve cached data from data/temp_cache/ if exists."""
    if not key:
        return None
    try:
        h = hashlib.md5(key.encode('utf-8')).hexdigest()
        fpath = os.path.join(TEMP_CACHE_DIR, f"{h}.cache")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None

def set_session_cache(key: str, data):
    """Save data into data/temp_cache/."""
    if not key:
        return
    try:
        h = hashlib.md5(key.encode('utf-8')).hexdigest()
        fpath = os.path.join(TEMP_CACHE_DIR, f"{h}.cache")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def cleanup_temp_cache():
    """Wipe all temporary session cache files."""
    try:
        if os.path.exists(TEMP_CACHE_DIR):
            shutil.rmtree(TEMP_CACHE_DIR, ignore_errors=True)
            os.makedirs(TEMP_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

CATEGORIES = ["movies", "series", "anime", "games", "software"]

CORE_GENRES = [
    "Боевик", "Комедия", "Драма", "Фантастика", "Триллер",
    "Детектив", "Ужасы", "Приключения", "Криминал", "Фэнтези",
    "Мелодрама", "Мультфильм", "Документальный", "Военный"
]
DEFAULT_GENRES = CORE_GENRES

def normalize_text(s):
    if s is None:
        return ""
    return str(s).lower().replace('ё', 'е').replace('Ё', 'е').strip()

def _py_lower(s):
    if s is None:
        return ""
    return str(s).lower().replace('ё', 'е').replace('Ё', 'е')

def _py_like(pattern, value):
    if pattern is None or value is None:
        return False
    pat = str(pattern).lower().replace('ё', 'е').replace('Ё', 'е')
    val = str(value).lower().replace('ё', 'е').replace('Ё', 'е')
    parts = []
    for ch in pat:
        if ch == '%':
            parts.append('.*')
        elif ch == '_':
            parts.append('.')
        else:
            parts.append(re.escape(ch))
    regex = '^' + ''.join(parts) + '$'
    return bool(re.match(regex, val, re.DOTALL))

def clean_dedup_key(title_ru, title_en, year=0):
    # Strip common noise, bracketed metadata, release groups, and season tags to properly group releases into one title
    def strip_noise(t):
        if not t:
            return ""
        # 1. Strip all square brackets [ ... ] (e.g. [02x01-03 из 10], [1080p], [LostFilm], [RePack])
        s = re.sub(r'\[.*?\]', ' ', t)
        # 2. Strip parentheses with season/episode/version/repack noise
        s = re.sub(r'\([^)]*(?:сезон|сери|s\d+|repack|верси|v\s*\d|update|озвуч|г\.|dlc|bonus)[^)]*\)', ' ', s, flags=re.I)
        # 3. Strip standalone release tags
        s = re.sub(r'\b(?:repack|portable|rip|web-dl|web-dlrip|hdtv|bdrip|remux|dlc|bonus)\b', ' ', s, flags=re.I)
        # 4. Strip free-text season/episode patterns
        s = re.sub(r'\b(?:сезон\s*\d+|\d+\s*сезон|\d+x\d+|s\d+(?:e\d+)?|серии?\s*\d+[\d\-]*|из\s*\d+)\b', ' ', s, flags=re.I)
        # 5. Strip trailing or isolated years
        s = re.sub(r'[-–—]\s*(?:19|20)\d{2}\b', ' ', s)
        s = re.sub(r'\b(?:19|20)\d{2}\b', ' ', s)
        # 6. Normalize punctuation and spaces
        s = re.sub(r'[^\w\s]', ' ', normalize_text(s))
        return re.sub(r'\s+', ' ', s).strip()

    # Priority 1: Canonical Russian title (avoids splits caused by uploader typos in English titles)
    ru = strip_noise(title_ru)
    if ru and len(ru) >= 3:
        return f"ru_{ru}"
    # Priority 2: English title
    en = strip_noise(title_en)
    if en and len(en) >= 3:
        return f"en_{en}"
    raw = strip_noise(title_ru or title_en or "")
    return f"raw_{raw}"

def normalize_category(category):
    if not category:
        return "movies"
    cat = str(category).lower().strip()
    if cat in ("nashe_kino", "films", "film", "movie"):
        return "movies"
    if cat in ("serial", "serials", "tv"):
        return "series"
    if cat in ("soft", "apps", "programs"):
        return "software"
    if cat in ("game",):
        return "games"
    if cat in CATEGORIES:
        return cat
    return "movies"

def get_db_path(category="movies"):
    cat = normalize_category(category)
    return os.path.join(DATA_DIR, f"{cat}.db")

def get_connection(category="movies"):
    db_path = get_db_path(category)
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.create_function("lower", 1, _py_lower)
    conn.create_function("like", 2, _py_like)
    conn.create_function("NORM", 1, normalize_text)
    conn.create_function("DEDUP_KEY", 3, clean_dedup_key)
    return conn

def init_db():
    for cat in CATEGORIES:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torrent_id TEXT UNIQUE,
            category TEXT,
            title TEXT,
            title_ru TEXT,
            title_en TEXT,
            year INTEGER,
            date_added TEXT,
            date_ts INTEGER,
            size_gb REAL,
            size_str TEXT,
            seeds INTEGER DEFAULT 0,
            peers INTEGER DEFAULT 0,
            quality TEXT,
            video_info TEXT,
            audio_info TEXT,
            audio_tracks TEXT,
            voiceover TEXT,
            subtitles TEXT,
            genre TEXT,
            director TEXT,
            actors TEXT,
            description TEXT,
            country TEXT,
            duration TEXT,
            imdb_rating REAL DEFAULT 0.0,
            kp_rating REAL DEFAULT 0.0,
            poster_url TEXT,
            torrent_url TEXT,
            magnet_url TEXT,
            source_url TEXT,
            seasons_info TEXT,
            mediainfo TEXT,
            user_status TEXT DEFAULT 'new',
            updated_at INTEGER,
            episodes_released INTEGER DEFAULT 0,
            episodes_total INTEGER DEFAULT 0,
            seasons_count INTEGER DEFAULT 0,
            streaming_platform TEXT DEFAULT '',
            voice_studio TEXT DEFAULT '',
            repack_author TEXT DEFAULT '',
            release_format TEXT DEFAULT '',
            crack_status TEXT DEFAULT '',
            app_version TEXT DEFAULT '',
            screenshots_json TEXT DEFAULT '[]',
            shikimori_rating REAL DEFAULT 0.0,
            mal_rating REAL DEFAULT 0.0,
            metacritic_critic REAL DEFAULT 0.0,
            metacritic_user REAL DEFAULT 0.0,
            opencritic_rating REAL DEFAULT 0.0,
            has_subtitles INTEGER DEFAULT 0,
            is_ongoing INTEGER DEFAULT 0,
            anime_type TEXT DEFAULT '',
            software_category TEXT DEFAULT '',
            system_reqs TEXT DEFAULT '',
            repack_features TEXT DEFAULT '',
            steam_rating TEXT DEFAULT '',
            developer TEXT DEFAULT '',
            publisher TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            engine TEXT DEFAULT '',
            release_date TEXT DEFAULT ''
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ignored_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torrent_id TEXT UNIQUE,
            category TEXT,
            title TEXT,
            title_ru TEXT,
            title_en TEXT,
            year INTEGER,
            genre TEXT,
            kp_rating REAL DEFAULT 0.0,
            imdb_rating REAL DEFAULT 0.0,
            created_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torrent_id TEXT UNIQUE,
            category TEXT,
            title TEXT,
            title_ru TEXT,
            title_en TEXT,
            year INTEGER,
            genre TEXT,
            kp_rating REAL DEFAULT 0.0,
            imdb_rating REAL DEFAULT 0.0,
            poster_url TEXT,
            created_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS crawl_progress (
            category TEXT,
            year INTEGER,
            next_page INTEGER DEFAULT 1,
            PRIMARY KEY (category, year)
        )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_cat_date ON releases(category, date_ts DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cat_size ON releases(category, size_gb)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cat_rating ON releases(category, imdb_rating, kp_rating)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_releases_status ON releases(category, user_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_releases_studio ON releases(category, voice_studio)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_releases_format ON releases(category, release_format)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_releases_repack ON releases(category, repack_author)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ign_title ON ignored_releases(category, title_ru, year)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_watch_title ON watchlist_releases(category, title_ru, year)")
        conn.commit()
        conn.close()

    # Migration from legacy radar.db or radar.db.migrated if category databases are empty
    migrated_src = (RADAR_DB + ".migrated") if os.path.exists(RADAR_DB + ".migrated") else (RADAR_DB if os.path.exists(RADAR_DB) else None)
    if migrated_src:
        try:
            r_conn = sqlite3.connect(migrated_src)
            r_conn.row_factory = sqlite3.Row
            r_cur = r_conn.cursor()
            
            for cat in CATEGORIES:
                target_conn = get_connection(cat)
                t_cur = target_conn.cursor()
                t_cur.execute("SELECT count(*) FROM releases")
                if t_cur.fetchone()[0] == 0:
                    if cat == "movies":
                        r_cur.execute("SELECT * FROM releases WHERE category IN ('movies', 'nashe_kino') OR category IS NULL")
                    else:
                        r_cur.execute("SELECT * FROM releases WHERE category = ?", (cat,))
                    rows = [dict(r) for r in r_cur.fetchall()]
                    for row in rows:
                        cols = [k for k in row.keys() if k != "id"]
                        placeholders = ", ".join(["?"] * len(cols))
                        col_str = ", ".join(cols)
                        t_cur.execute(f"INSERT OR IGNORE INTO releases ({col_str}) VALUES ({placeholders})", [row[c] for c in cols])
                    
                    # Migrate watchlist if empty
                    t_cur.execute("SELECT count(*) FROM watchlist_releases")
                    if t_cur.fetchone()[0] == 0:
                        r_cur.execute("SELECT * FROM watchlist_releases WHERE category = ?", (cat,))
                        w_rows = [dict(r) for r in r_cur.fetchall()]
                        for row in w_rows:
                            cols = [k for k in row.keys() if k != "id"]
                            placeholders = ", ".join(["?"] * len(cols))
                            col_str = ", ".join(cols)
                            t_cur.execute(f"INSERT OR IGNORE INTO watchlist_releases ({col_str}) VALUES ({placeholders})", [row[c] for c in cols])
                    
                    # Migrate ignored if empty
                    t_cur.execute("SELECT count(*) FROM ignored_releases")
                    if t_cur.fetchone()[0] == 0:
                        r_cur.execute("SELECT * FROM ignored_releases WHERE category = ?", (cat,))
                        i_rows = [dict(r) for r in r_cur.fetchall()]
                        for row in i_rows:
                            cols = [k for k in row.keys() if k != "id"]
                            placeholders = ", ".join(["?"] * len(cols))
                            col_str = ", ".join(cols)
                            t_cur.execute(f"INSERT OR IGNORE INTO ignored_releases ({col_str}) VALUES ({placeholders})", [row[c] for c in cols])
                    
                    target_conn.commit()
                target_conn.close()
            r_conn.close()
        except Exception:
            pass

def upsert_release(data):
    cat = normalize_category(data.get("category", "movies"))
    conn = get_connection(cat)
    c = conn.cursor()
    now = int(time.time())
    fields = [
        "torrent_id", "category", "title", "title_ru", "title_en", "year",
        "date_added", "date_ts", "size_gb", "size_str", "seeds", "peers",
        "quality", "video_info", "audio_info", "audio_tracks", "voiceover",
        "subtitles", "genre", "director", "actors", "description", "country",
        "duration", "imdb_rating", "kp_rating", "poster_url", "torrent_url",
        "magnet_url", "source_url", "seasons_info", "mediainfo", "user_status", "updated_at",
        "episodes_released", "episodes_total", "seasons_count", "streaming_platform",
        "voice_studio", "repack_author", "release_format", "crack_status",
        "app_version", "screenshots_json", "shikimori_rating", "mal_rating",
        "metacritic_critic", "metacritic_user", "opencritic_rating", "has_subtitles",
        "is_ongoing", "anime_type", "software_category", "system_reqs", "repack_features",
        "steam_rating", "developer", "publisher", "platform", "engine", "release_date"
    ]
    data["updated_at"] = now
    if "user_status" not in data or not data["user_status"]:
        data["user_status"] = "new"

    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    
    conflict_clauses = [
        "category = excluded.category",
        "title = excluded.title",
        "title_ru = CASE WHEN excluded.title_ru != '' THEN excluded.title_ru ELSE releases.title_ru END",
        "title_en = CASE WHEN excluded.title_en != '' THEN excluded.title_en ELSE releases.title_en END",
        "year = CASE WHEN excluded.year > 0 THEN excluded.year ELSE releases.year END",
        "date_added = excluded.date_added",
        "date_ts = excluded.date_ts",
        "size_gb = CASE WHEN excluded.size_gb > 0 THEN excluded.size_gb ELSE releases.size_gb END",
        "size_str = CASE WHEN excluded.size_str != '' THEN excluded.size_str ELSE releases.size_str END",
        "seeds = excluded.seeds",
        "peers = excluded.peers",
        "quality = CASE WHEN excluded.quality != '' AND excluded.quality != '1080p' THEN excluded.quality ELSE COALESCE(NULLIF(releases.quality, ''), excluded.quality) END",
        "video_info = CASE WHEN excluded.video_info != '' THEN excluded.video_info ELSE releases.video_info END",
        "audio_info = CASE WHEN excluded.audio_info != '' THEN excluded.audio_info ELSE releases.audio_info END",
        "audio_tracks = CASE WHEN excluded.audio_tracks != '' AND excluded.audio_tracks != '[]' THEN excluded.audio_tracks ELSE releases.audio_tracks END",
        "voiceover = CASE WHEN excluded.voiceover != '' THEN excluded.voiceover ELSE releases.voiceover END",
        "subtitles = CASE WHEN excluded.subtitles != '' AND excluded.subtitles != '[]' THEN excluded.subtitles ELSE releases.subtitles END",
        "genre = CASE WHEN excluded.genre != '' THEN excluded.genre ELSE releases.genre END",
        "director = CASE WHEN excluded.director != '' THEN excluded.director ELSE releases.director END",
        "actors = CASE WHEN excluded.actors != '' THEN excluded.actors ELSE releases.actors END",
        "description = CASE WHEN excluded.description != '' THEN excluded.description ELSE releases.description END",
        "country = CASE WHEN excluded.country != '' THEN excluded.country ELSE releases.country END",
        "duration = CASE WHEN excluded.duration != '' THEN excluded.duration ELSE releases.duration END",
        "imdb_rating = CASE WHEN excluded.imdb_rating > 0 THEN excluded.imdb_rating ELSE releases.imdb_rating END",
        "kp_rating = CASE WHEN excluded.kp_rating > 0 THEN excluded.kp_rating ELSE releases.kp_rating END",
        "poster_url = CASE WHEN excluded.poster_url != '' THEN excluded.poster_url ELSE releases.poster_url END",
        "torrent_url = excluded.torrent_url",
        "magnet_url = CASE WHEN excluded.magnet_url != '' THEN excluded.magnet_url ELSE releases.magnet_url END",
        "source_url = excluded.source_url",
        "seasons_info = CASE WHEN excluded.seasons_info != '' AND excluded.seasons_info != '[]' THEN excluded.seasons_info ELSE releases.seasons_info END",
        "mediainfo = CASE WHEN excluded.mediainfo != '' THEN excluded.mediainfo ELSE releases.mediainfo END",
        "user_status = COALESCE(NULLIF(releases.user_status, ''), excluded.user_status, 'new')",
        "updated_at = excluded.updated_at",
        "episodes_released = CASE WHEN excluded.episodes_released > 0 THEN excluded.episodes_released ELSE releases.episodes_released END",
        "episodes_total = CASE WHEN excluded.episodes_total > 0 THEN excluded.episodes_total ELSE releases.episodes_total END",
        "seasons_count = CASE WHEN excluded.seasons_count > COALESCE(releases.seasons_count, 0) THEN excluded.seasons_count ELSE releases.seasons_count END",
        "streaming_platform = CASE WHEN excluded.streaming_platform != '' THEN excluded.streaming_platform ELSE releases.streaming_platform END",
        "voice_studio = CASE WHEN excluded.voice_studio != '' THEN excluded.voice_studio ELSE releases.voice_studio END",
        "repack_author = CASE WHEN excluded.repack_author != '' THEN excluded.repack_author ELSE releases.repack_author END",
        "release_format = CASE WHEN excluded.release_format != '' THEN excluded.release_format ELSE releases.release_format END",
        "crack_status = CASE WHEN excluded.crack_status != '' THEN excluded.crack_status ELSE releases.crack_status END",
        "app_version = CASE WHEN excluded.app_version != '' THEN excluded.app_version ELSE releases.app_version END",
        "screenshots_json = CASE WHEN excluded.screenshots_json != '' AND excluded.screenshots_json != '[]' THEN excluded.screenshots_json ELSE releases.screenshots_json END",
        "shikimori_rating = CASE WHEN excluded.shikimori_rating > 0 THEN excluded.shikimori_rating ELSE releases.shikimori_rating END",
        "mal_rating = CASE WHEN excluded.mal_rating > 0 THEN excluded.mal_rating ELSE releases.mal_rating END",
        "metacritic_critic = CASE WHEN excluded.metacritic_critic > 0 THEN excluded.metacritic_critic ELSE releases.metacritic_critic END",
        "metacritic_user = CASE WHEN excluded.metacritic_user > 0 THEN excluded.metacritic_user ELSE releases.metacritic_user END",
        "opencritic_rating = CASE WHEN excluded.opencritic_rating > 0 THEN excluded.opencritic_rating ELSE releases.opencritic_rating END",
        "has_subtitles = CASE WHEN excluded.has_subtitles > 0 THEN excluded.has_subtitles ELSE releases.has_subtitles END",
        "is_ongoing = CASE WHEN excluded.is_ongoing > 0 THEN excluded.is_ongoing ELSE releases.is_ongoing END",
        "anime_type = CASE WHEN excluded.anime_type != '' THEN excluded.anime_type ELSE releases.anime_type END",
        "software_category = CASE WHEN excluded.software_category != '' THEN excluded.software_category ELSE releases.software_category END",
        "system_reqs = CASE WHEN excluded.system_reqs != '' THEN excluded.system_reqs ELSE releases.system_reqs END",
        "repack_features = CASE WHEN excluded.repack_features != '' THEN excluded.repack_features ELSE releases.repack_features END",
        "steam_rating = CASE WHEN excluded.steam_rating != '' THEN excluded.steam_rating ELSE releases.steam_rating END",
        "developer = CASE WHEN excluded.developer != '' THEN excluded.developer ELSE releases.developer END",
        "publisher = CASE WHEN excluded.publisher != '' THEN excluded.publisher ELSE releases.publisher END",
        "platform = CASE WHEN excluded.platform != '' THEN excluded.platform ELSE releases.platform END",
        "engine = CASE WHEN excluded.engine != '' THEN excluded.engine ELSE releases.engine END",
        "release_date = CASE WHEN excluded.release_date != '' THEN excluded.release_date ELSE releases.release_date END"
    ]
    update_clause = ", ".join(conflict_clauses)

    sql = f"""
    INSERT INTO releases ({columns})
    VALUES ({placeholders})
    ON CONFLICT(torrent_id) DO UPDATE SET {update_clause}
    """
    values = [data.get(f) for f in fields]
    c.execute(sql, values)
    conn.commit()
    conn.close()

def update_tracker_stats(torrent_id, seeds, peers, size_gb, size_str, date_str, date_ts, category=None):
    target_cats = [normalize_category(category)] if category else CATEGORIES
    now = int(time.time())
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("""
            UPDATE releases
            SET seeds = ?, peers = ?, size_gb = ?, size_str = ?, date_added = ?, date_ts = ?, updated_at = ?
            WHERE torrent_id = ?
        """, (seeds, peers, size_gb, size_str, date_str, date_ts, now, str(torrent_id)))
        updated = c.rowcount > 0
        conn.commit()
        conn.close()
        if updated:
            break

def clear_cache(category=None):
    target_cats = [normalize_category(category)] if category else CATEGORIES
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("DELETE FROM releases")
        conn.commit()
        conn.close()

def get_release_by_id(item_id, category=None):
    target_cats = [normalize_category(category)] if category else CATEGORIES
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT * FROM releases WHERE id = ? OR torrent_id = ?", (item_id, str(item_id)))
        row = c.fetchone()
        if row:
            item = dict(row)
            c.execute("""
                SELECT id, torrent_id, category, title, title_ru, title_en, quality, size_str, size_gb, seeds, peers, 
                       torrent_url, magnet_url, voiceover, voice_studio, subtitles, has_subtitles, release_format, crack_status
                FROM releases
                WHERE DEDUP_KEY(COALESCE(NULLIF(title_ru, ''), title), title_en, year) = DEDUP_KEY(COALESCE(NULLIF(?, ''), ?), ?, ?)
                  AND id != ?
                ORDER BY seeds DESC, size_gb DESC
            """, (item.get("title_ru"), item.get("title"), item.get("title_en"), item.get("year", 0), item["id"]))
            alt_rows = [dict(r) for r in c.fetchall()]
            item["alternatives"] = alt_rows
            conn.close()
            return item
        conn.close()
    return None

def query_season_releases(clean_title, season_num=0, category="series", is_pack=False):
    norm_cat = normalize_category(category)
    conn = get_connection(norm_cat)
    c = conn.cursor()
    clean_k = clean_dedup_key(clean_title, "")
    
    c.execute(f"""
        SELECT id, torrent_id, category, title, title_ru, title_en, year, date_added, date_ts,
               size_gb, size_str, seeds, peers, quality, voiceover, voice_studio, subtitles,
               has_subtitles, episodes_released, episodes_total, seasons_count, torrent_url,
               magnet_url, streaming_platform
        FROM releases
        WHERE category = ?
          AND (
              DEDUP_KEY(COALESCE(NULLIF(title_ru, ''), title), title_en, year) = ?
              OR lower(title_ru) LIKE ?
              OR lower(title) LIKE ?
          )
        ORDER BY episodes_released DESC, seeds DESC, size_gb DESC
    """, (norm_cat, clean_k, f"%{clean_title.lower()}%", f"%{clean_title.lower()}%"))
    
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    
    if is_pack:
        # Multi-season pack releases (e.g. [S01-S02], [1-3 сезоны], [Все сезоны])
        filtered = []
        for r in rows:
            raw_t = (r.get("title") or "").lower()
            m_range = re.search(r'(?:\[|\()(?:S?\d{1,2}\s*[-–]\s*S?\d{1,2}|(?:сезон[ыа]?|season[s]?)\s*\d{1,2}\s*[-–]\s*\d{1,2}|\d{1,2}\s*[-–]\s*\d{1,2}\s*сезон)', raw_t, re.I)
            if m_range or re.search(r'все\s+сезоны|полный\s+сезон|антология', raw_t, re.I):
                filtered.append(r)
        return filtered

    if not season_num or int(season_num) == 0:
        return rows
        
    s_num = int(season_num)
    filtered = []
    for r in rows:
        raw_t = (r.get("title") or "").lower()
        
        # 1. Direct season patterns
        patterns = [
            rf'(?:\[|\()\s*s0?{s_num}(?:[^\d]|$)',
            rf'\bсезон\s*{s_num}\b',
            rf'\b{s_num}\s*сезон\b',
            rf'(?:\[|\()\s*0?{s_num}x',
            rf'\bs{s_num:02d}\b',
            rf'\[s0?{s_num}\]'
        ]
        matched = any(bool(re.search(p, raw_t, re.I)) for p in patterns)
        
        # 2. Check if part of a multi-season range that covers s_num
        m_range = re.search(r'(?:\[|\()(?:S?(\d{1,2})\s*[-–]\s*S?(\d{1,2})|(?:сезон[ыа]?|season[s]?)\s*(\d{1,2})\s*[-–]\s*(\d{1,2})|(\d{1,2})\s*[-–]\s*(\d{1,2})\s*сезон)', raw_t, re.I)
        if m_range:
            start_s = int(m_range.group(1) or m_range.group(3) or m_range.group(5))
            end_s = int(m_range.group(2) or m_range.group(4) or m_range.group(6))
            if start_s <= s_num <= end_s:
                matched = True

        anime_movie_patterns = (
            r'\b(?:фильм|movie|the movie|полнометраж|полнометражный|gekijouban|film|guren no kizuna|'
            r'алые\s*узы|слёзы\s*синего\s*моря)\b'
        )

        if matched:
            # Strict isolation: if querying anime seasons, exclude full-length movies (>60 min or classified as movie)
            if norm_cat == "anime" or category == "anime":
                dur_str = r.get("duration") or ""
                dur_min = 0
                m_hms = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', dur_str)
                if m_hms:
                    dur_min = int(m_hms.group(1)) * 60 + int(m_hms.group(2))
                else:
                    m_m = re.search(r'(\d+)\s*мин', dur_str, re.I)
                    if m_m:
                        dur_min = int(m_m.group(1))

                is_anime_movie = (
                    r.get("anime_type") == "Полнометражный фильм"
                    or dur_min > 60
                    or bool(re.search(anime_movie_patterns, raw_t, re.I))
                )
                if is_anime_movie and not bool(re.search(anime_movie_patterns, clean_title.lower(), re.I)):
                    continue
            filtered.append(r)
        elif s_num == 1 and not bool(re.search(r'(?:\[|\()(?:сезон\s*[2-9]|[2-9]\s*сезон|0?[2-9]x|s0?[2-9])', raw_t, re.I)):
            # Strict isolation: exclude anime movies from Season 1
            if norm_cat == "anime" or category == "anime":
                dur_str = r.get("duration") or ""
                dur_min = 0
                m_hms = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', dur_str)
                if m_hms:
                    dur_min = int(m_hms.group(1)) * 60 + int(m_hms.group(2))
                else:
                    m_m = re.search(r'(\d+)\s*мин', dur_str, re.I)
                    if m_m:
                        dur_min = int(m_m.group(1))

                is_anime_movie = (
                    r.get("anime_type") == "Полнометражный фильм"
                    or dur_min > 60
                    or bool(re.search(anime_movie_patterns, raw_t, re.I))
                )
                if is_anime_movie and not bool(re.search(anime_movie_patterns, clean_title.lower(), re.I)):
                    continue

                # If title has a colon with standalone feature subtitle without episode/season tags, exclude from season 1
                has_ep_tags = bool(re.search(r'\[\s*(?:\d+-\d+|\d+\s*из\s*\d+|\d+x\d+|s0?1)\s*\]', raw_t, re.I))
                if not has_ep_tags and ':' in (r.get("title_ru") or ''):
                    continue
            filtered.append(r)
            
    return filtered

def query_releases(
    category="movies", min_rating=0.0, max_size=999.0, qualities=None,
    genre="all", year="all", search=None, page=1, limit=15, deduplicate=True,
    origin="all", streaming="all", voiceover="all", ongoing="all",
    has_subtitles=False, anime_type="all", repack_author="all",
    release_format="all", crack_status="all", software_category="all"
):
    norm_cat = normalize_category(category)
    conn = get_connection(norm_cat)
    c = conn.cursor()

    conditions = []
    params = []

    # Category matching
    if category == "nashe_kino":
        conditions.append("(category = 'nashe_kino' OR country LIKE '%Россия%' OR country LIKE '%СССР%')")
    elif category:
        conditions.append("category = ?")
        params.append(category)

    # Exclude items marked 'ignored' or in watchlist
    conditions.append("releases.user_status NOT IN ('watchlist', 'ignored', 'watchlist_alt', 'ignored_alt')")
    conditions.append("""
        NOT EXISTS (
            SELECT 1 FROM ignored_releases ig 
            WHERE ig.torrent_id = releases.torrent_id
               OR (
                   ig.category = ? 
                   AND (
                       (ig.title_ru IS NOT NULL AND releases.title_ru IS NOT NULL AND ig.title_ru != '' AND lower(trim(ig.title_ru)) = lower(trim(releases.title_ru)))
                       OR (ig.title IS NOT NULL AND releases.title IS NOT NULL AND ig.title != '' AND lower(trim(ig.title)) = lower(trim(releases.title)))
                   )
                   AND (ig.year = releases.year OR ig.year = 0 OR releases.year = 0)
               )
        )
    """)
    params.append(category)
    conditions.append("""
        NOT EXISTS (
            SELECT 1 FROM watchlist_releases wl 
            WHERE wl.torrent_id = releases.torrent_id
               OR (
                   wl.category = ? 
                   AND (
                       (wl.title_ru IS NOT NULL AND releases.title_ru IS NOT NULL AND wl.title_ru != '' AND lower(trim(wl.title_ru)) = lower(trim(releases.title_ru)))
                       OR (wl.title IS NOT NULL AND releases.title IS NOT NULL AND wl.title != '' AND lower(trim(wl.title)) = lower(trim(releases.title)))
                   )
                   AND (wl.year = releases.year OR wl.year = 0 OR releases.year = 0)
               )
        )
    """)
    params.append(category)

    # Origin filter (Russian vs Foreign vs All) — strictly applied ONLY for movies and series
    if category in ("movies", "series"):
        if origin == "russian":
            conditions.append("""(
                country LIKE '%Россия%' 
                OR country LIKE '%СССР%' 
                OR country LIKE '%РФ%' 
                OR country LIKE '%Беларусь%' 
                OR category = 'nashe_kino'
                OR (
                    (country IS NULL OR country = '') 
                    AND (title_en IS NULL OR title_en = '') 
                    AND title NOT LIKE '%/%'
                )
            )""")
        elif origin == "foreign":
            conditions.append("""(
                country NOT LIKE '%Россия%' 
                AND country NOT LIKE '%СССР%' 
                AND country NOT LIKE '%РФ%' 
                AND country NOT LIKE '%Беларусь%' 
                AND category != 'nashe_kino'
                AND (
                    (country IS NOT NULL AND country != '')
                    OR (title_en IS NOT NULL AND title_en != '')
                    OR title LIKE '%/%'
                )
            )""")

    # Year filter
    if year and str(year) != "all":
        y_str = str(year).strip().lower()
        if y_str in ("< 2000", "<2000", "pre-2000", "pre2000", "old"):
            conditions.append("year < 2000 AND year > 0")
        else:
            try:
                y_val = int(year)
                if y_val > 0:
                    conditions.append("year = ?")
                    params.append(y_val)
            except ValueError:
                pass

    # Rating filter
    if min_rating > 0:
        conditions.append("""(
            (kp_rating IS NOT NULL AND kp_rating >= ?) 
            OR (imdb_rating IS NOT NULL AND imdb_rating >= ?)
            OR (shikimori_rating IS NOT NULL AND shikimori_rating >= ?)
            OR (metacritic_critic IS NOT NULL AND metacritic_critic >= (? * 10))
            OR (opencritic_rating IS NOT NULL AND opencritic_rating >= (? * 10))
        )""")
        params.extend([min_rating, min_rating, min_rating, min_rating, min_rating])

    # Size filter
    if max_size < 999.0:
        conditions.append("size_gb <= ?")
        params.append(max_size)

    # Quality filter
    if qualities and len(qualities) > 0 and qualities != ["all"]:
        q_conds = []
        for q in qualities:
            q_clean = q.strip().lower()
            if q_clean in ("< 720p", "<720p", "480p", "sd"):
                q_conds.append("(quality IN ('480p', '576p', 'SD', '< 720p') OR quality NOT IN ('1080p', '720p', '2160p', '4K'))")
            elif q_clean in ("720p", "1080p", "2160p", "4k"):
                q_conds.append(f"quality = '{q.strip()}'")
            else:
                q_conds.append("quality LIKE ?")
                params.append(f"%{q}%")
        if q_conds:
            conditions.append("(" + " OR ".join(q_conds) + ")")

    # Genre filter (case-insensitive)
    if genre and genre != "all":
        conditions.append("lower(genre) LIKE ?")
        params.append(f"%{genre.strip().lower()}%")

    # Series-specific filters
    if category == "series":
        if streaming and streaming != "all":
            conditions.append("lower(streaming_platform) LIKE ?")
            params.append(f"%{streaming.strip().lower()}%")
        if voiceover and voiceover != "all":
            conditions.append("(lower(voiceover) LIKE ? OR lower(voice_studio) LIKE ?)")
            params.extend([f"%{voiceover.strip().lower()}%", f"%{voiceover.strip().lower()}%"])
        if ongoing in (True, "true", "1", "ongoing"):
            conditions.append("is_ongoing = 1")
        elif ongoing in ("finished", "ended", "complete"):
            conditions.append("(is_ongoing = 0 OR is_ongoing IS NULL)")

    # Anime-specific filters
    if category == "anime":
        if anime_type and anime_type != "all":
            a_low = anime_type.strip().lower()
            if 'тв' in a_low or 'tv' in a_low:
                conditions.append("(lower(anime_type) LIKE '%тв-сериал%' OR lower(anime_type) LIKE '%tv-сериал%' OR anime_type = '')")
            else:
                conditions.append("lower(anime_type) LIKE ?")
                params.append(f"%{a_low}%")
        if voiceover and voiceover != "all":
            conditions.append("(lower(voiceover) LIKE ? OR lower(voice_studio) LIKE ?)")
            params.extend([f"%{voiceover.strip().lower()}%", f"%{voiceover.strip().lower()}%"])
        if has_subtitles:
            conditions.append("(has_subtitles = 1 OR lower(subtitles) != '' AND lower(subtitles) != '[]' AND lower(subtitles) != 'нет')")

    # Games-specific filters
    if category == "games":
        if repack_author and repack_author != "all":
            r_auth = repack_author.strip().lower()
            conditions.append("(lower(repack_author) LIKE ? OR lower(title) LIKE ?)")
            params.extend([f"%{r_auth}%", f"%{r_auth}%"])
        if release_format and release_format != "all":
            fmt_l = release_format.strip().lower()
            if fmt_l == "repack":
                conditions.append("(lower(release_format) = 'repack' OR lower(title) LIKE '%repack%')")
            elif fmt_l == "portable":
                conditions.append("(lower(release_format) = 'portable' OR lower(title) LIKE '%portable%')")
            elif fmt_l in ("лицензия", "license", "scene"):
                conditions.append("(lower(release_format) IN ('лицензия', 'license', 'scene') OR lower(title) LIKE '%лицензия%')")
            else:
                conditions.append("lower(release_format) LIKE ?")
                params.append(f"%{fmt_l}%")
        if crack_status and crack_status != "all":
            conditions.append("lower(crack_status) LIKE ?")
            params.append(f"%{crack_status.strip().lower()}%")

    # Software-specific filters
    if category == "software":
        if software_category and software_category != "all":
            conditions.append("lower(software_category) LIKE ?")
            params.append(f"%{software_category.strip().lower()}%")
        if release_format and release_format != "all":
            conditions.append("(lower(release_format) LIKE ? OR lower(title) LIKE ?)")
            params.extend([f"%{release_format.strip().lower()}%", f"%{release_format.strip().lower()}%"])
        if repack_author and repack_author != "all":
            s_auth = repack_author.strip().lower()
            conditions.append("(lower(repack_author) LIKE ? OR lower(title) LIKE ?)")
            params.extend([f"%{s_auth}%", f"%{s_auth}%"])

    # Search filter (case-insensitive Unicode)
    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        conditions.append("(lower(title_ru) LIKE ? OR lower(title_en) LIKE ? OR lower(title) LIKE ? OR lower(actors) LIKE ? OR lower(director) LIKE ?)")
        params.extend([s, s, s, s, s])

    where_clause = " WHERE " + " AND ".join(conditions)

    if deduplicate:
        dedup_sql = f"""
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY DEDUP_KEY(COALESCE(NULLIF(title_ru, ''), title), title_en, year)
            ORDER BY 
                CASE 
                    WHEN user_status IN ('watchlist', 'ignored') THEN 0
                    WHEN user_status IN ('watchlist_alt', 'ignored_alt') THEN 1
                    ELSE 2 
                END ASC,
                COALESCE(seasons_count, 0) DESC,
                seeds DESC, size_gb DESC
        ) as rn
        FROM releases
        {where_clause}
        """
        count_sql = f"SELECT COUNT(*) FROM ({dedup_sql}) AS ranked WHERE rn = 1"
        c.execute(count_sql, params)
        total_count = c.fetchone()[0]

        offset = (page - 1) * limit
        data_sql = f"""
        SELECT r.* FROM releases r
        JOIN ({dedup_sql}) ranked ON r.id = ranked.id AND ranked.rn = 1
        ORDER BY r.date_ts DESC, r.seeds DESC
        LIMIT ? OFFSET ?
        """
        c.execute(data_sql, params + [limit, offset])
    else:
        count_sql = f"SELECT COUNT(*) FROM releases {where_clause}"
        c.execute(count_sql, params)
        total_count = c.fetchone()[0]

        offset = (page - 1) * limit
        data_sql = f"""
        SELECT * FROM releases
        {where_clause}
        ORDER BY date_ts DESC, seeds DESC
        LIMIT ? OFFSET ?
        """
        c.execute(data_sql, params + [limit, offset])

    raw_rows = [dict(r) for r in c.fetchall()]
    rows = []
    
    c.execute("SELECT torrent_id, lower(trim(title_ru)), year FROM watchlist_releases")
    w_rows = c.fetchall()
    watch_tids = {str(r[0]) for r in w_rows if r[0]}
    watch_titles = {(r[1], r[2]) for r in w_rows if r[1] and r[2]}

    c.execute("SELECT torrent_id, lower(trim(title_ru)), year FROM ignored_releases")
    i_rows = c.fetchall()
    ign_tids = {str(r[0]) for r in i_rows if r[0]}
    ign_titles = {(r[1], r[2]) for r in i_rows if r[1] and r[2]}

    for row in raw_rows:
        tid = str(row.get("torrent_id", ""))
        tru = (row.get("title_ru") or "").strip().lower()
        yr = row.get("year") or 0
        raw_status = row.get("user_status", "new")

        if tid in watch_tids or (tru, yr) in watch_titles or raw_status in ("watchlist", "watchlist_alt"):
            row["user_status"] = "watchlist"
        elif tid in ign_tids or (tru, yr) in ign_titles or raw_status in ("ignored", "ignored_alt"):
            row["user_status"] = "ignored"
        else:
            row["user_status"] = "new"
        rows.append(row)
    conn.close()

    return {
        "items": rows,
        "total": total_count,
        "page": page,
        "limit": limit,
        "pages": (total_count + limit - 1) // limit if total_count > 0 else 1
    }

def add_to_watchlist(torrent_id, category=None):
    rel = get_release_by_id(torrent_id, category=category)
    cat = normalize_category(rel.get("category") if rel else category)
    conn = get_connection(cat)
    c = conn.cursor()
    now = int(time.time())
    if rel:
        c.execute("""
            INSERT OR REPLACE INTO watchlist_releases 
            (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, poster_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(torrent_id), cat, rel.get('title'), rel.get('title_ru'),
            rel.get('title_en'), rel.get('year'), rel.get('genre'), rel.get('kp_rating'),
            rel.get('imdb_rating'), rel.get('poster_url'), now
        ))
        c.execute("UPDATE releases SET user_status = 'watchlist', updated_at = ? WHERE torrent_id = ?",
                  (now, str(torrent_id)))
        t_ru = rel.get('title_ru')
        t_raw = rel.get('title')
        yr = rel.get('year', 0)
        if t_ru:
            c.execute("""
                UPDATE releases SET user_status = 'watchlist_alt', updated_at = ?
                WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND torrent_id != ?
            """, (now, t_ru, yr, str(torrent_id)))
        if t_raw:
            c.execute("""
                UPDATE releases SET user_status = 'watchlist_alt', updated_at = ?
                WHERE lower(trim(title)) = lower(trim(?)) AND torrent_id != ?
            """, (now, t_raw, str(torrent_id)))
    else:
        c.execute("""
            INSERT OR IGNORE INTO watchlist_releases (torrent_id, category, created_at) VALUES (?, ?, ?)
        """, (str(torrent_id), cat, now))
    conn.commit()
    conn.close()

def remove_from_watchlist(torrent_id, category=None):
    rel = get_release_by_id(torrent_id, category=category)
    cat = normalize_category(rel.get("category") if rel else category)
    conn = get_connection(cat)
    c = conn.cursor()
    now = int(time.time())
    c.execute("DELETE FROM watchlist_releases WHERE torrent_id = ?", (str(torrent_id),))
    c.execute("UPDATE releases SET user_status = 'new', updated_at = ? WHERE torrent_id = ?",
              (now, str(torrent_id)))
    if rel and rel.get('title_ru'):
        c.execute("DELETE FROM watchlist_releases WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND category = ?",
                  (rel['title_ru'], rel.get('year', 0), cat))
        c.execute("""
            UPDATE releases SET user_status = 'new', updated_at = ?
            WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND category = ?
        """, (now, rel['title_ru'], rel.get('year', 0), cat))
    conn.commit()

    c.execute("SELECT 1 FROM watchlist_releases WHERE torrent_id = ?", (str(torrent_id),))
    still_in_watch = c.fetchone()
    conn.close()

    if not still_in_watch:
        try:
            poster_path = os.path.join(POSTERS_DIR, f"{torrent_id}.jpg")
            if os.path.exists(poster_path):
                os.remove(poster_path)
        except Exception:
            pass

def query_watchlist(category=None, search=None, page=1, limit=15):
    target_cats = [normalize_category(category)] if category and category != "all" else CATEGORIES
    all_items = []
    
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        conditions = []
        params = []
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            conditions.append("(lower(COALESCE(r.title_ru, w.title_ru)) LIKE ? OR lower(COALESCE(r.title_en, w.title_en)) LIKE ? OR lower(COALESCE(r.title, w.title)) LIKE ?)")
            params.extend([s, s, s])
        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        
        query = f"""
            SELECT 
                w.torrent_id,
                COALESCE(r.id, w.id) as id,
                COALESCE(r.category, w.category, '{cat}') as category,
                COALESCE(r.title, w.title) as title,
                COALESCE(r.title_ru, w.title_ru) as title_ru,
                COALESCE(r.title_en, w.title_en) as title_en,
                COALESCE(r.year, w.year) as year,
                COALESCE(r.genre, w.genre) as genre,
                COALESCE(r.poster_url, w.poster_url) as poster_url,
                COALESCE(r.kp_rating, w.kp_rating, 0.0) as kp_rating,
                COALESCE(r.imdb_rating, w.imdb_rating, 0.0) as imdb_rating,
                COALESCE(r.shikimori_rating, 0.0) as shikimori_rating,
                COALESCE(r.mal_rating, 0.0) as mal_rating,
                COALESCE(r.size_gb, 0.0) as size_gb,
                COALESCE(r.size_str, '') as size_str,
                COALESCE(r.seeds, 0) as seeds,
                COALESCE(r.peers, 0) as peers,
                COALESCE(r.quality, '1080p') as quality,
                COALESCE(r.release_format, '') as release_format,
                COALESCE(r.repack_author, '') as repack_author,
                COALESCE(r.torrent_url, '') as torrent_url,
                COALESCE(r.magnet_url, '') as magnet_url,
                COALESCE(r.country, '') as country,
                COALESCE(r.date_added, '') as date_added,
                'watchlist' as user_status,
                w.created_at
            FROM watchlist_releases w
            LEFT JOIN releases r ON r.torrent_id = w.torrent_id
            {where_clause}
        """
        c.execute(query, params)
        all_items.extend([dict(r) for r in c.fetchall()])
        conn.close()

    all_items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    total = len(all_items)
    offset = (page - 1) * limit
    items = all_items[offset:offset + limit]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

def add_to_ignored(torrent_id, category=None):
    rel = get_release_by_id(torrent_id, category=category)
    cat = normalize_category(rel.get("category") if rel else category)
    conn = get_connection(cat)
    c = conn.cursor()
    now = int(time.time())
    if rel:
        title_ru = rel.get('title_ru')
        year = rel.get('year')
        c.execute("""
            INSERT OR REPLACE INTO ignored_releases 
            (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(torrent_id), cat, rel.get('title'), title_ru,
            rel.get('title_en'), year, rel.get('genre'), rel.get('kp_rating'),
            rel.get('imdb_rating'), now
        ))
        c.execute("UPDATE releases SET user_status = 'ignored', updated_at = ? WHERE torrent_id = ?",
                  (now, str(torrent_id)))
        t_raw = rel.get('title')
        if title_ru:
            c.execute("""
                UPDATE releases SET user_status = 'ignored_alt', updated_at = ?
                WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND torrent_id != ?
            """, (now, title_ru, year, str(torrent_id)))
        if t_raw:
            c.execute("""
                UPDATE releases SET user_status = 'ignored_alt', updated_at = ?
                WHERE lower(trim(title)) = lower(trim(?)) AND torrent_id != ?
            """, (now, t_raw, str(torrent_id)))
        
        # Free session cache storage
        c.execute("""
            UPDATE releases 
            SET description = NULL, mediainfo = NULL, screenshots_json = '[]', audio_tracks = NULL
            WHERE torrent_id = ?
        """, (str(torrent_id),))
    else:
        c.execute("""
            INSERT OR IGNORE INTO ignored_releases (torrent_id, category, created_at) VALUES (?, ?, ?)
        """, (str(torrent_id), cat, now))
    conn.commit()
    conn.close()

def restore_from_ignored(torrent_id, category=None):
    rel = get_release_by_id(torrent_id, category=category)
    cat = normalize_category(rel.get("category") if rel else category)
    conn = get_connection(cat)
    c = conn.cursor()
    c.execute("SELECT title_ru, year FROM ignored_releases WHERE torrent_id = ?", (str(torrent_id),))
    row = c.fetchone()
    now = int(time.time())
    c.execute("DELETE FROM ignored_releases WHERE torrent_id = ?", (str(torrent_id),))
    c.execute("UPDATE releases SET user_status = 'new', updated_at = ? WHERE torrent_id = ?",
              (now, str(torrent_id)))
    if row and row['title_ru']:
        c.execute("DELETE FROM ignored_releases WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND category = ?",
                  (row['title_ru'], row['year'], cat))
        c.execute("""
            UPDATE releases SET user_status = 'new', updated_at = ?
            WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND category = ?
        """, (now, row['title_ru'], row['year'], cat))
    conn.commit()
    conn.close()

def query_ignored(category=None, search=None, page=1, limit=15):
    target_cats = [normalize_category(category)] if category and category != "all" else CATEGORIES
    all_items = []

    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        conditions = []
        params = []
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            conditions.append("(lower(title_ru) LIKE ? OR lower(title_en) LIKE ? OR lower(title) LIKE ?)")
            params.extend([s, s, s])
        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        c.execute(f"SELECT * FROM ignored_releases {where_clause}", params)
        all_items.extend([dict(r) for r in c.fetchall()])
        conn.close()

    all_items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    total = len(all_items)
    offset = (page - 1) * limit
    items = all_items[offset:offset + limit]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

def is_ignored(torrent_id, title_ru="", year=0, category=None):
    target_cats = [normalize_category(category)] if category else CATEGORIES
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT 1 FROM ignored_releases WHERE torrent_id = ?", (str(torrent_id),))
        if c.fetchone():
            conn.close()
            return True
        if title_ru and year and year > 0:
            c.execute("SELECT 1 FROM ignored_releases WHERE LOWER(TRIM(title_ru)) = LOWER(TRIM(?)) AND year = ?",
                      (title_ru, int(year)))
            if c.fetchone():
                conn.close()
                return True
        conn.close()
    return False

def is_watchlist(torrent_id, title_ru="", year=0, category=None):
    target_cats = [normalize_category(category)] if category else CATEGORIES
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT 1 FROM watchlist_releases WHERE torrent_id = ?", (str(torrent_id),))
        if c.fetchone():
            conn.close()
            return True
        if title_ru and year and year > 0:
            c.execute("SELECT 1 FROM watchlist_releases WHERE LOWER(TRIM(title_ru)) = LOWER(TRIM(?)) AND year = ?",
                      (title_ru, int(year)))
            if c.fetchone():
                conn.close()
                return True
        conn.close()
    return False

def get_curation_counts(category=None):
    by_category = {}
    tot_wc = 0
    tot_ic = 0
    for cat in CATEGORIES:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(lower(trim(title_ru)), ''), lower(trim(title)), torrent_id) || '_' || COALESCE(year, 0)) FROM watchlist_releases")
        wc = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(lower(trim(title_ru)), ''), lower(trim(title)), torrent_id) || '_' || COALESCE(year, 0)) FROM ignored_releases")
        ic = c.fetchone()[0]
        conn.close()
        by_category[cat] = {"watchlist": wc, "ignored": ic}
        tot_wc += wc
        tot_ic += ic

    return {
        "watchlist": tot_wc,
        "ignored": tot_ic,
        "category_watchlist": by_category.get(category, {}).get("watchlist", 0) if category else tot_wc,
        "category_ignored": by_category.get(category, {}).get("ignored", 0) if category else tot_ic,
        "by_category": by_category
    }

def get_all_curation_counts():
    result = {"total": {"watchlist": 0, "ignored": 0}}
    for cat in CATEGORIES:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(lower(trim(title_ru)), ''), lower(trim(title)), torrent_id) || '_' || COALESCE(year, 0)) FROM watchlist_releases")
        wc = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(lower(trim(title_ru)), ''), lower(trim(title)), torrent_id) || '_' || COALESCE(year, 0)) FROM ignored_releases")
        ic = c.fetchone()[0]
        conn.close()
        result[cat] = {"watchlist": wc, "ignored": ic}
        result["total"]["watchlist"] += wc
        result["total"]["ignored"] += ic
    return result

def cleanup_session_cache():
    try:
        keep_tids = set()
        for cat in CATEGORIES:
            conn = get_connection(cat)
            c = conn.cursor()
            c.execute("SELECT torrent_id FROM watchlist_releases")
            watch_rows = c.fetchall()
            for r in watch_rows:
                if r[0]:
                    keep_tids.add(str(r[0]))
            
            c.execute("""
                DELETE FROM releases 
                WHERE user_status NOT IN ('watchlist', 'watchlist_alt')
                  AND torrent_id NOT IN (SELECT torrent_id FROM watchlist_releases)
            """)
            conn.commit()
            conn.isolation_level = None
            conn.execute("VACUUM")
            conn.close()

        if os.path.exists(POSTERS_DIR):
            for fname in os.listdir(POSTERS_DIR):
                tid = os.path.splitext(fname)[0]
                if tid not in keep_tids:
                    fpath = os.path.join(POSTERS_DIR, fname)
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        cleanup_temp_cache()
        return True
    except Exception:
        return False

def get_crawl_page(category, year):
    conn = get_connection(category)
    c = conn.cursor()
    c.execute("SELECT next_page FROM crawl_progress WHERE category = ? AND year = ?", (category, int(year or 0)))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 1

def advance_crawl_page(category, year):
    conn = get_connection(category)
    c = conn.cursor()
    cur = get_crawl_page(category, year)
    nxt = cur + 1
    c.execute("INSERT OR REPLACE INTO crawl_progress (category, year, next_page) VALUES (?, ?, ?)",
              (category, int(year or 0), nxt))
    conn.commit()
    conn.close()
    return nxt

ANIME_GENRES = [
    "Боевик", "Детектив", "Драма", "Исекай", "Комедия", "Меха", "Мистика",
    "Повседневность", "Приключения", "Романтика", "Сёнэн", "Сёдзё", "Триллер",
    "Фантастика", "Фэнтези"
]
GAME_GENRES = [
    "Action", "RPG", "Шутер", "Стратегия", "Приключения", "Гонки", "Симулятор",
    "Спорт", "Хоррор", "Инди", "Файтинг", "Квест"
]
SOFTWARE_CATEGORIES = [
    "Система", "Офис", "Графика", "Мультимедиа", "Безопасность", "Интернет",
    "Утилиты", "Драйверы", "Аудио", "Видео"
]

def get_distinct_genres(category="movies"):
    if category in ("movies", "series"):
        base_genres = set(CORE_GENRES)
    elif category == "anime":
        base_genres = set(ANIME_GENRES)
    elif category == "games":
        base_genres = set(GAME_GENRES)
    elif category == "software":
        base_genres = set(SOFTWARE_CATEGORIES)
    else:
        base_genres = set(CORE_GENRES)

    conn = get_connection(category)
    c = conn.cursor()
    c.execute("SELECT genre FROM releases WHERE genre != ''")
    rows = c.fetchall()
    conn.close()

    genres = set(base_genres)
    for r in rows:
        g_str = r[0]
        for g in re.split(r'[,/|;]+', g_str):
            clean_g = g.strip().capitalize()
            if clean_g and len(clean_g) > 2 and not any(ch.isdigit() for ch in clean_g):
                genres.add(clean_g)

    return sorted(list(genres))

def get_distinct_years(category="movies"):
    years = [str(y) for y in range(2026, 1999, -1)]
    years.append("< 2000")
    return years

def update_release_poster(torrent_id, poster_url, category=None):
    if not torrent_id or not poster_url:
        return
    target_cats = [normalize_category(category)] if category else CATEGORIES
    for cat in target_cats:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("UPDATE releases SET poster_url = ? WHERE torrent_id = ?", (poster_url, str(torrent_id)))
        updated = c.rowcount > 0
        c.execute("UPDATE watchlist_releases SET poster_url = ? WHERE torrent_id = ?", (poster_url, str(torrent_id)))
        conn.commit()
        conn.close()
        if updated:
            break

def sync_watchlist_to_releases():
    for cat in CATEGORIES:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT * FROM watchlist_releases")
        rows = [dict(r) for r in c.fetchall()]
        now = int(time.time())
        for r in rows:
            tid = r['torrent_id']
            c.execute("SELECT 1 FROM releases WHERE torrent_id = ?", (tid,))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO releases (
                        torrent_id, category, title, title_ru, title_en, year, genre,
                        kp_rating, imdb_rating, poster_url, user_status, updated_at, date_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'watchlist', ?, ?)
                """, (
                    tid, r.get('category', cat), r.get('title', ''), r.get('title_ru', ''),
                    r.get('title_en', ''), r.get('year', 0), r.get('genre', ''),
                    r.get('kp_rating', 0.0), r.get('imdb_rating', 0.0), r.get('poster_url', ''),
                    now, r.get('created_at', now)
                ))
            else:
                c.execute("UPDATE releases SET user_status = 'watchlist', updated_at = ? WHERE torrent_id = ?", (now, tid))
        conn.commit()
        conn.close()

def sync_ignored_to_releases():
    for cat in CATEGORIES:
        conn = get_connection(cat)
        c = conn.cursor()
        c.execute("SELECT * FROM ignored_releases")
        rows = [dict(r) for r in c.fetchall()]
        now = int(time.time())
        for r in rows:
            tid = r['torrent_id']
            c.execute("SELECT 1 FROM releases WHERE torrent_id = ?", (tid,))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO releases (
                        torrent_id, category, title, title_ru, title_en, year, genre,
                        kp_rating, imdb_rating, user_status, updated_at, date_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ignored', ?, ?)
                """, (
                    tid, r.get('category', cat), r.get('title', ''), r.get('title_ru', ''),
                    r.get('title_en', ''), r.get('year', 0), r.get('genre', ''),
                    r.get('kp_rating', 0.0), r.get('imdb_rating', 0.0), now, r.get('created_at', now)
                ))
            else:
                c.execute("UPDATE releases SET user_status = 'ignored', updated_at = ? WHERE torrent_id = ?", (now, tid))
        conn.commit()
        conn.close()

init_db()
sync_watchlist_to_releases()
sync_ignored_to_releases()
