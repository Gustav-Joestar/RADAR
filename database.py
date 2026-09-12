import sqlite3
import os
import time
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "radar.db")

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
    update_clause = ", ".join([f"{f}=excluded.{f}" for f in fields if f != "torrent_id"])

    sql = f"""
    INSERT INTO releases ({columns})
    VALUES ({placeholders})
    ON CONFLICT(torrent_id) DO UPDATE SET {update_clause}
    """
    values = [data.get(f) for f in fields]
    c.execute(sql, values)
    conn.commit()
    conn.close()

def query_releases(category="movies", days=7, min_rating=0.0, max_size=15.0,
                   qualities=None, genre=None, search=None, page=1, limit=15):
    conn = get_connection()
    c = conn.cursor()

    conditions = ["category = ?"]
    params = [category]

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

    # Count
    count_sql = f"SELECT COUNT(*) FROM releases {where_clause}"
    c.execute(count_sql, params)
    total_count = c.fetchone()[0]

    # Paginated data
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
    conn.close()
    return dict(row) if row else None

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

init_db()
