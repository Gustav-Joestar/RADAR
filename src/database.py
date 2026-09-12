import sqlite3
import os
import time
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "radar.db")

CORE_GENRES = [
    "Боевик", "Комедия", "Драма", "Фантастика", "Триллер",
    "Детектив", "Ужасы", "Приключения", "Криминал", "Фэнтези",
    "Мелодрама", "Мультфильм", "Документальный", "Военный"
]
DEFAULT_GENRES = CORE_GENRES

def _py_lower(s):
    if s is None:
        return ""
    return str(s).lower()

def _py_like(pattern, value):
    if pattern is None or value is None:
        return False
    pat = str(pattern).lower()
    val = str(value).lower()
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

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.create_function("lower", 1, _py_lower)
    conn.create_function("like", 2, _py_like)
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
        user_status TEXT DEFAULT 'new',
        updated_at INTEGER
    )
    """)
    # Migration: add user_status if table already existed without it
    c.execute("PRAGMA table_info(releases)")
    cols = [r[1] for r in c.fetchall()]
    if "user_status" not in cols:
        c.execute("ALTER TABLE releases ADD COLUMN user_status TEXT DEFAULT 'new'")

    c.execute("""
    CREATE TABLE IF NOT EXISTS ignored_releases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        torrent_id TEXT UNIQUE,
        category TEXT DEFAULT 'movies',
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
        category TEXT DEFAULT 'movies',
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_ign_title ON ignored_releases(title_ru, year)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_watch_title ON watchlist_releases(title_ru, year)")

    # Migrate any existing watchlist items from releases into watchlist_releases
    c.execute("""
        INSERT OR IGNORE INTO watchlist_releases 
        (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, poster_url, created_at)
        SELECT torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, poster_url, COALESCE(updated_at, 0)
        FROM releases WHERE user_status = 'watchlist'
    """)

    # Migrate any existing ignored items from releases into ignored_releases
    c.execute("""
        INSERT OR IGNORE INTO ignored_releases 
        (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, created_at)
        SELECT torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, COALESCE(updated_at, 0)
        FROM releases WHERE user_status = 'ignored'
    """)

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
        "magnet_url", "source_url", "seasons_info", "mediainfo", "user_status", "updated_at"
    ]
    data["updated_at"] = now
    if "user_status" not in data or not data["user_status"]:
        data["user_status"] = "new"

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
        "user_status = COALESCE(NULLIF(releases.user_status, ''), excluded.user_status, 'new')",
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

def query_releases(category="movies", min_rating=0.0, max_size=15.0,
                   qualities=None, genre=None, year="2026", search=None,
                   page=1, limit=15, deduplicate=True, days=0, origin="all"):
    conn = get_connection()
    c = conn.cursor()

    conditions = ["category = ?"]
    params = [category]

    # If NOT searching by title, strictly exclude watchlist and ignored from the discovery feed!
    # If searching by title, return all matching items regardless of user_status (so status badges can show)
    if not (search and search.strip()):
        conditions.append("(releases.user_status IS NULL OR releases.user_status = 'new')")
        conditions.append("releases.torrent_id NOT IN (SELECT torrent_id FROM ignored_releases)")
        conditions.append("releases.torrent_id NOT IN (SELECT torrent_id FROM watchlist_releases)")
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM ignored_releases ig 
                WHERE ig.title_ru IS NOT NULL AND ig.year IS NOT NULL 
                  AND lower(trim(ig.title_ru)) = lower(trim(releases.title_ru)) 
                  AND ig.year = releases.year
            )
        """)
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM watchlist_releases wl 
                WHERE wl.title_ru IS NOT NULL AND wl.year IS NOT NULL 
                  AND lower(trim(wl.title_ru)) = lower(trim(releases.title_ru)) 
                  AND wl.year = releases.year
            )
        """)

    # Origin filter (Russian vs Foreign vs All)
    if origin == "russian":
        conditions.append("(country LIKE '%Россия%' OR country LIKE '%СССР%' OR country LIKE '%РФ%' OR category = 'nashe_kino')")
    elif origin == "foreign":
        conditions.append("(country NOT LIKE '%Россия%' AND country NOT LIKE '%СССР%' AND country NOT LIKE '%РФ%' AND category != 'nashe_kino')")

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

    # Genre filter (case-insensitive)
    if genre and genre != "all":
        conditions.append("lower(genre) LIKE ?")
        params.append(f"%{genre.strip().lower()}%")

    # Search filter (case-insensitive Unicode)
    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        conditions.append("(lower(title_ru) LIKE ? OR lower(title_en) LIKE ? OR lower(title) LIKE ? OR lower(actors) LIKE ? OR lower(director) LIKE ?)")
        params.extend([s, s, s, s, s])

    where_clause = " WHERE " + " AND ".join(conditions)

    if deduplicate:
        # Deduplicate by grouping movie title and year, prioritizing active user statuses, then picking release with highest seeds
        dedup_sql = f"""
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY LOWER(TRIM(COALESCE(NULLIF(title_ru, ''), title))), year
            ORDER BY 
                CASE 
                    WHEN user_status IN ('watchlist', 'ignored') THEN 0
                    WHEN user_status IN ('watchlist_alt', 'ignored_alt') THEN 1
                    ELSE 2 
                END ASC,
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
    
    # Pre-fetch watchlist and ignored sets to ensure fast and accurate badge marking
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

def add_to_watchlist(torrent_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM releases WHERE torrent_id = ?", (str(torrent_id),))
    row = c.fetchone()
    now = int(time.time())
    if row:
        title_ru = row['title_ru']
        year = row['year']
        c.execute("""
            INSERT OR REPLACE INTO watchlist_releases 
            (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, poster_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(torrent_id), row['category'], row['title'], row['title_ru'],
            row['title_en'], row['year'], row['genre'], row['kp_rating'],
            row['imdb_rating'], row['poster_url'], now
        ))
        c.execute("UPDATE releases SET user_status = 'watchlist', updated_at = ? WHERE torrent_id = ?",
                  (now, str(torrent_id)))
        # Remove from ignored if was there
        c.execute("DELETE FROM ignored_releases WHERE torrent_id = ? OR (lower(trim(title_ru)) = lower(trim(?)) AND year = ?)",
                  (str(torrent_id), title_ru, year))
        # Mark other releases of this same movie
        if title_ru:
            c.execute("""
                UPDATE releases SET user_status = 'watchlist_alt', updated_at = ?
                WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND torrent_id != ?
            """, (now, title_ru, year, str(torrent_id)))
    else:
        c.execute("UPDATE releases SET user_status = 'watchlist', updated_at = ? WHERE torrent_id = ?",
                  (now, str(torrent_id)))
    conn.commit()
    conn.close()

def remove_from_watchlist(torrent_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT title_ru, year FROM releases WHERE torrent_id = ?", (str(torrent_id),))
    row = c.fetchone()
    now = int(time.time())
    c.execute("DELETE FROM watchlist_releases WHERE torrent_id = ?", (str(torrent_id),))
    c.execute("UPDATE releases SET user_status = 'new', updated_at = ? WHERE torrent_id = ?",
              (now, str(torrent_id)))
    if row and row['title_ru']:
        c.execute("DELETE FROM watchlist_releases WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ?",
                  (row['title_ru'], row['year']))
        c.execute("""
            UPDATE releases SET user_status = 'new', updated_at = ?
            WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ?
        """, (now, row['title_ru'], row['year']))
    conn.commit()
    conn.close()

def query_watchlist(search=None, page=1, limit=15):
    conn = get_connection()
    c = conn.cursor()
    conditions = ["user_status = 'watchlist'"]
    params = []
    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        conditions.append("(lower(title_ru) LIKE ? OR lower(title_en) LIKE ? OR lower(title) LIKE ?)")
        params.extend([s, s, s])
    where_clause = " WHERE " + " AND ".join(conditions)

    c.execute(f"SELECT COUNT(*) FROM releases {where_clause}", params)
    total = c.fetchone()[0]

    offset = (page - 1) * limit
    c.execute(f"SELECT * FROM releases {where_clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
    items = [dict(r) for r in c.fetchall()]
    conn.close()
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

def add_to_ignored(torrent_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM releases WHERE torrent_id = ?", (str(torrent_id),))
    row = c.fetchone()
    now = int(time.time())
    if row:
        title_ru = row['title_ru']
        year = row['year']
        c.execute("""
            INSERT OR REPLACE INTO ignored_releases 
            (torrent_id, category, title, title_ru, title_en, year, genre, kp_rating, imdb_rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(torrent_id), row['category'], row['title'], row['title_ru'],
            row['title_en'], row['year'], row['genre'], row['kp_rating'],
            row['imdb_rating'], now
        ))
        c.execute("DELETE FROM watchlist_releases WHERE torrent_id = ? OR (lower(trim(title_ru)) = lower(trim(?)) AND year = ?)",
                  (str(torrent_id), title_ru, year))
        # Keep release with status 'ignored' so title search can show status badge
        c.execute("UPDATE releases SET user_status = 'ignored', updated_at = ? WHERE torrent_id = ?",
                  (now, str(torrent_id)))
        if title_ru:
            c.execute("""
                UPDATE releases SET user_status = 'ignored_alt', updated_at = ?
                WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ? AND torrent_id != ?
            """, (now, title_ru, year, str(torrent_id)))
        conn.commit()
    conn.close()

def restore_from_ignored(torrent_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM ignored_releases WHERE torrent_id = ?", (str(torrent_id),))
    c.execute("SELECT title_ru, year FROM releases WHERE torrent_id = ?", (str(torrent_id),))
    row = c.fetchone()
    now = int(time.time())
    c.execute("UPDATE releases SET user_status = 'new', updated_at = ? WHERE torrent_id = ?",
              (now, str(torrent_id)))
    if row and row['title_ru']:
        c.execute("DELETE FROM ignored_releases WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ?",
                  (row['title_ru'], row['year']))
        c.execute("""
            UPDATE releases SET user_status = 'new', updated_at = ?
            WHERE lower(trim(title_ru)) = lower(trim(?)) AND year = ?
        """, (now, row['title_ru'], row['year']))
    conn.commit()
    conn.close()

def query_ignored(search=None, page=1, limit=15):
    conn = get_connection()
    c = conn.cursor()
    conditions = ["1=1"]
    params = []
    if search and search.strip():
        s = f"%{search.strip()}%"
        conditions.append("(title_ru LIKE ? OR title_en LIKE ? OR title LIKE ?)")
        params.extend([s, s, s])
    where_clause = " WHERE " + " AND ".join(conditions)

    c.execute(f"SELECT COUNT(*) FROM ignored_releases {where_clause}", params)
    total = c.fetchone()[0]

    offset = (page - 1) * limit
    c.execute(f"SELECT * FROM ignored_releases {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
    items = [dict(r) for r in c.fetchall()]
    conn.close()
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

def is_ignored(torrent_id, title_ru="", year=0):
    conn = get_connection()
    c = conn.cursor()
    # Check by torrent_id
    c.execute("SELECT 1 FROM ignored_releases WHERE torrent_id = ?", (str(torrent_id),))
    if c.fetchone():
        conn.close()
        return True
    # Check by title and year if provided
    if title_ru and year and year > 0:
        c.execute("SELECT 1 FROM ignored_releases WHERE LOWER(TRIM(title_ru)) = LOWER(TRIM(?)) AND year = ?",
                  (title_ru, int(year)))
        if c.fetchone():
            conn.close()
            return True
    conn.close()
    return False

def is_watchlist(torrent_id, title_ru="", year=0):
    conn = get_connection()
    c = conn.cursor()
    # Check by torrent_id
    c.execute("SELECT 1 FROM watchlist_releases WHERE torrent_id = ?", (str(torrent_id),))
    if c.fetchone():
        conn.close()
        return True
    # Check by title and year if provided
    if title_ru and year and year > 0:
        c.execute("SELECT 1 FROM watchlist_releases WHERE LOWER(TRIM(title_ru)) = LOWER(TRIM(?)) AND year = ?",
                  (title_ru, int(year)))
        if c.fetchone():
            conn.close()
            return True
    conn.close()
    return False

def get_curation_counts():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT lower(trim(title_ru)) || '_' || year) FROM watchlist_releases")
    w_count = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT lower(trim(title_ru)) || '_' || year) FROM ignored_releases")
    i_count = c.fetchone()[0]
    conn.close()
    return {"watchlist": w_count, "ignored": i_count}

def get_crawl_page(category, year):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT next_page FROM crawl_progress WHERE category = ? AND year = ?", (category, int(year or 0)))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 1

def advance_crawl_page(category, year):
    conn = get_connection()
    c = conn.cursor()
    cur = get_crawl_page(category, year)
    nxt = cur + 1
    c.execute("INSERT OR REPLACE INTO crawl_progress (category, year, next_page) VALUES (?, ?, ?)",
              (category, int(year or 0), nxt))
    conn.commit()
    conn.close()
    return nxt

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
    if category in ("movies", "series"):
        return CORE_GENRES
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT genre FROM releases WHERE category = ? AND genre != ''", (category,))
    rows = c.fetchall()
    conn.close()

    genres = set(CORE_GENRES if category in ("movies", "series") else [])
    for r in rows:
        g_str = r[0]
        for g in re.split(r'[,/|;]+', g_str):
            clean_g = g.strip().capitalize()
            if clean_g and len(clean_g) > 2:
                genres.add(clean_g)

    return sorted(list(genres))

def get_distinct_years(category="movies"):
    # Return concrete years 2026 down to 2000, plus "< 2000"
    years = [str(y) for y in range(2026, 1999, -1)]
    years.append("< 2000")
    return years

def sync_ignored_to_releases():
    """Ensure any releases in ignored_releases also exist in releases with user_status = 'ignored'"""
    conn = get_connection()
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
                tid, r.get('category', 'movies'), r.get('title', ''), r.get('title_ru', ''),
                r.get('title_en', ''), r.get('year', 0), r.get('genre', ''),
                r.get('kp_rating', 0.0), r.get('imdb_rating', 0.0), now, r.get('created_at', now)
            ))
        else:
            c.execute("UPDATE releases SET user_status = 'ignored', updated_at = ? WHERE torrent_id = ?", (now, tid))
    conn.commit()
    conn.close()

init_db()
sync_ignored_to_releases()
