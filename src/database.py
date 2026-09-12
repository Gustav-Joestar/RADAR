import sqlite3
import os
import time
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "radar.db")

DEFAULT_GENRES = [
    "Боевик", "Комедия", "Драма", "Фантастика", "Триллер",
    "Детектив", "Ужасы", "Приключения", "Криминал", "Фэнтези",
    "Мелодрама", "Мультфильм", "Документальный", "Семейный",
    "Военный", "Биография", "Исторический", "Спорт", "Аниме"
]

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
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
        updated_at INTEGER
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_cat_date ON releases(category, date_ts DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cat_size ON releases(category, size_gb)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cat_rating ON releases(category, imdb_rating, kp_rating)")
    conn.commit()
    conn.close()

def upsert_release(data):
    conn = get_connection()
    c = conn.cursor()
    now = int(time.time())
    fields = [
        "torrent_id", "category", "title", "title_ru", "title_en", "year",
        "date_added", "date_ts", "size_gb", "size_str", "seeds", "peers",
        "quality", "video_info", "audio_info", "audio_tracks", "voiceover",
        "subtitles", "genre", "director", "actors", "description", "country",
        "duration", "imdb_rating", "kp_rating", "poster_url", "torrent_url",
        "magnet_url", "source_url", "seasons_info", "mediainfo", "updated_at"
    ]
    data["updated_at"] = now
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    
    # Smart update clause: NEVER overwrite cached posters, ratings, or descriptions with empty/zero defaults
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
        "updated_at = excluded.updated_at"
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

def update_tracker_stats(torrent_id, seeds, peers, size_gb, size_str, date_str, date_ts):
    conn = get_connection()
    c = conn.cursor()
    now = int(time.time())
    c.execute("""
        UPDATE releases
        SET seeds = ?, peers = ?, size_gb = ?, size_str = ?, date_added = ?, date_ts = ?, updated_at = ?
        WHERE torrent_id = ?
    """, (seeds, peers, size_gb, size_str, date_str, date_ts, now, str(torrent_id)))
    conn.commit()
    conn.close()

def clear_cache():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM releases")
    c.execute("VACUUM")
    conn.commit()
    conn.close()

def query_releases(category="movies", days=7, min_rating=0.0, max_size=15.0,
                   qualities=None, genre=None, year="2026", search=None,
                   page=1, limit=15, deduplicate=True):
    conn = get_connection()
    c = conn.cursor()

    conditions = ["category = ?"]
    params = [category]

    # Year filter
    if year and str(year) != "all":
        try:
            y_val = int(year)
            if y_val > 0:
                conditions.append("year = ?")
                params.append(y_val)
        except ValueError:
            pass

    # Date filter
    if days and days > 0:
        cutoff = int(time.time()) - (days * 86400)
        conditions.append("date_ts >= ?")
        params.append(cutoff)

    # Size filter
    if max_size and max_size > 0:
        conditions.append("size_gb <= ?")
        params.append(max_size)

    # Rating filter (only applied if min_rating > 0)
    if min_rating and min_rating > 0 and category in ("movies", "series", "anime"):
        conditions.append("(imdb_rating >= ? OR kp_rating >= ?)")
        params.append(min_rating)
        params.append(min_rating)

    # Quality filter
    if qualities and len(qualities) > 0 and category in ("movies", "series", "anime"):
        q_conds = []
        for q in qualities:
            q_conds.append("quality LIKE ?")
            params.append(f"%{q}%")
        conditions.append("(" + " OR ".join(q_conds) + ")")

    # Genre filter
    if genre and genre != "all":
        conditions.append("genre LIKE ?")
        params.append(f"%{genre}%")

    # Search filter
    if search and search.strip():
        s = f"%{search.strip()}%"
        conditions.append("(title_ru LIKE ? OR title_en LIKE ? OR title LIKE ? OR actors LIKE ? OR director LIKE ?)")
        params.extend([s, s, s, s, s])

    where_clause = " WHERE " + " AND ".join(conditions)

    if deduplicate:
        # Deduplicate by grouping movie title and year, picking release with highest seeds
        dedup_sql = f"""
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY LOWER(TRIM(COALESCE(NULLIF(title_ru, ''), title))), year
            ORDER BY seeds DESC, size_gb DESC
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

    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "items": rows,
        "total": total_count,
        "page": page,
        "limit": limit,
        "pages": (total_count + limit - 1) // limit if total_count > 0 else 1
    }

def get_release_by_id(item_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM releases WHERE id = ? OR torrent_id = ?", (item_id, str(item_id)))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    
    item = dict(row)
    # Find alternative releases for this title
    title_key = item.get("title_ru") or item.get("title_en") or item.get("title") or ""
    year = item.get("year", 0)
    c.execute("""
        SELECT id, torrent_id, quality, size_str, seeds, peers, torrent_url, magnet_url, title
        FROM releases
        WHERE (LOWER(TRIM(title_ru)) = LOWER(TRIM(?)) OR LOWER(TRIM(title)) = LOWER(TRIM(?)))
          AND id != ?
        ORDER BY seeds DESC
    """, (title_key, title_key, item["id"]))
    alt_rows = [dict(r) for r in c.fetchall()]
    item["alternatives"] = alt_rows
    conn.close()
    return item

def get_distinct_genres(category="movies"):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT genre FROM releases WHERE category = ? AND genre != ''", (category,))
    rows = c.fetchall()
    conn.close()

    genres = set(DEFAULT_GENRES if category in ("movies", "series", "anime") else [])
    for r in rows:
        g_str = r[0]
        for g in re.split(r'[,/|;]+', g_str):
            clean_g = g.strip().capitalize()
            if clean_g and len(clean_g) > 2:
                genres.add(clean_g)

    return sorted(list(genres))

def get_distinct_years(category="movies"):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT year FROM releases 
        WHERE category = ? AND year >= 1990 AND year <= 2030
        ORDER BY year DESC
    """, (category,))
    rows = c.fetchall()
    conn.close()
    years = [r[0] for r in rows if r[0]]
    if 2026 not in years:
        years.insert(0, 2026)
    return years

init_db()
