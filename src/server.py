import json
import mimetypes
import os
import re
import sys
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from concurrent.futures import ThreadPoolExecutor
import time

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import database
import tracker_engine
from logger import log, get_logs

PORT = 8765
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

LAST_HEARTBEAT = time.time()
SHUTDOWN_TIMER = None
HEARTBEAT_ACTIVE = False

ACTIVE_CRAWLS = {}
CRAWL_LOCK = threading.Lock()

POSTER_PRELOAD_POOL = ThreadPoolExecutor(max_workers=3)
PENDING_POSTER_TIDS = set()
POSTER_PRELOAD_LOCK = threading.Lock()

def queue_poster_preload(tid, category, title="", year=0, title_en=""):
    with POSTER_PRELOAD_LOCK:
        if tid in PENDING_POSTER_TIDS:
            return
        PENDING_POSTER_TIDS.add(tid)
    def worker():
        try:
            local_jpg = os.path.join(database.POSTERS_DIR, f"{tid}.jpg")
            if not os.path.exists(local_jpg):
                try:
                    tracker_engine.parse_full_details(int(tid))
                except Exception:
                    pass
            if not os.path.exists(local_jpg) and title:
                try:
                    web_p = tracker_engine.fetch_web_poster(title, int(year or 0), title_en, category)
                    if web_p:
                        tracker_engine.cache_poster_locally(str(tid), web_p)
                        database.update_release_poster(str(tid), f"/posters/{tid}.jpg")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with POSTER_PRELOAD_LOCK:
                PENDING_POSTER_TIDS.discard(tid)
    POSTER_PRELOAD_POOL.submit(worker)

def start_background_fill(category, year=0, genre="all"):
    with CRAWL_LOCK:
        thread = ACTIVE_CRAWLS.get(category)
        if thread and thread.is_alive():
            return
        def worker():
            log(f"⚡ [ЛАЙВ-ДОБОР] Фоновый поиск дополнительных раздач для [{category}]...", "INFO")
            if genre and genre != "all":
                q_genre = f"{genre} {year}" if year > 0 else genre
                log(f"⚡ [ЛАЙВ-ДОБОР] Поиск по жанру «{q_genre}» в [{category}]...", "INFO")
                try:
                    tracker_engine.search_tracker_by_query(q_genre, category)
                except Exception as e:
                    log(f"⚠️ Ошибка поиска по жанру: {e}", "DEBUG")

            for page_idx in range(4):
                try:
                    cnt = tracker_engine.scan_next_tracker_page(category, year)
                    if cnt == 0:
                        break
                except Exception as e:
                    log(f"⚠️ Ошибка фонового сканирования: {e}", "DEBUG")
                    break
            log(f"🏁 [ЛАЙВ-ДОБОР] Сканирование трекера для [{category}] завершено", "INFO")

        t = threading.Thread(target=worker, daemon=True)
        ACTIVE_CRAWLS[category] = t
        t.start()

def do_shutdown():
    log("🛑 [СЕРВЕР] Окно браузера закрыто пользователем. Очистка сессионного кэша и остановка процесса RADAR...", "INFO")
    try:
        database.cleanup_session_cache()
    except Exception:
        pass
    time.sleep(0.3)
    os._exit(0)

def cancel_shutdown():
    global SHUTDOWN_TIMER
    if SHUTDOWN_TIMER and SHUTDOWN_TIMER.is_alive():
        SHUTDOWN_TIMER.cancel()
        SHUTDOWN_TIMER = None

def schedule_shutdown(delay=3.5):
    global SHUTDOWN_TIMER
    cancel_shutdown()
    SHUTDOWN_TIMER = threading.Timer(delay, do_shutdown)
    SHUTDOWN_TIMER.daemon = True
    SHUTDOWN_TIMER.start()

def watchdog_monitor():
    # Grace period: wait 60s to allow user time to open browser
    time.sleep(60)
    while True:
        time.sleep(3)
        if HEARTBEAT_ACTIVE and (time.time() - LAST_HEARTBEAT > 120):
            log("🛑 [СЕРВЕР] Потеряна связь с окном браузера (>120 сек). Очистка сессионного кэша и остановка сервера RADAR...", "INFO")
            try:
                database.cleanup_session_cache()
            except Exception:
                pass
            time.sleep(0.3)
            os._exit(0)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class RadarRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif path == "/favicon.ico":
            self.serve_static(os.path.join(STATIC_DIR, "favicon.ico"))
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = os.path.join(STATIC_DIR, rel_path)
            self.serve_static(file_path)
        elif path == "/api/items":
            self.handle_api_items(params)
        elif path == "/api/items_poll":
            self.handle_api_items_poll(params)
        elif path == "/api/cards_status":
            self.handle_api_cards_status(params)
        elif path == "/api/item":
            self.handle_api_item(params)
        elif path == "/api/series_season_torrents":
            self.handle_api_series_season_torrents(params)
        elif path == "/api/watchlist":
            category = params.get("category", ["all"])[0]
            search = params.get("search", [""])[0]
            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["15"])[0])
            self.send_json(database.query_watchlist(category=category, search=search, page=page, limit=limit))
        elif path == "/api/ignored":
            category = params.get("category", ["all"])[0]
            search = params.get("search", [""])[0]
            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["15"])[0])
            self.send_json(database.query_ignored(category=category, search=search, page=page, limit=limit))
        elif path == "/api/counts":
            category = params.get("category", [None])[0]
            self.send_json(database.get_curation_counts(category=category))
        elif path == "/api/logs":
            self.send_json({"logs": get_logs()})
        elif path == "/api/genres":
            self.handle_api_genres(params)
        elif path == "/api/years":
            self.handle_api_years(params)
        elif path == "/api/alternatives_details":
            raw_ids = params.get("ids", [""])[0]
            if not raw_ids:
                self.send_json({"items": []})
            else:
                tids = [i.strip() for i in raw_ids.split(",") if i.strip()]
                res = []
                for tid in tids:
                    rel = database.get_release_by_id(tid)
                    if rel:
                        if not rel.get("voiceover") and not rel.get("subtitles"):
                            try:
                                parsed = tracker_engine.parse_full_details(tid)
                                if parsed:
                                    rel = parsed
                            except Exception:
                                pass
                        res.append(rel)
                self.send_json({"items": res})
        elif path == "/api/heartbeat":
            global LAST_HEARTBEAT, HEARTBEAT_ACTIVE
            LAST_HEARTBEAT = time.time()
            HEARTBEAT_ACTIVE = True
            cancel_shutdown()
            self.send_json({"status": "ok"})
        elif path == "/api/browser_closing":
            schedule_shutdown(3.5)
            self.send_json({"status": "closing"})
        elif path.startswith("/posters/"):
            poster_filename = os.path.basename(path)
            poster_path = os.path.join(database.POSTERS_DIR, poster_filename)
            if os.path.exists(poster_path):
                try:
                    with open(poster_path, "rb") as f:
                        h = f.read(32)
                    if not tracker_engine.is_valid_image_bytes(h):
                        os.remove(poster_path)
                except Exception:
                    pass

            if not os.path.exists(poster_path):
                # Attempt to fetch missing poster directly from torrent page
                tid_str = os.path.splitext(poster_filename)[0]
                log(f"🔄 [ПОСТЕР] Загрузка обложки #{tid_str} с торрент-страницы...", "INFO")
                try:
                    tracker_engine.parse_full_details(int(tid_str))
                    if os.path.exists(poster_path):
                        log(f"✅ [ПОСТЕР] Обложка #{tid_str} успешно загружена", "SUCCESS")
                    else:
                        log(f"⚠️ [ПОСТЕР] Обложка #{tid_str} не найдена на странице торрента", "WARNING")
                except Exception as e:
                    log(f"⚠️ Ошибка загрузки постера для #{tid_str}: {e}", "WARNING")
            if os.path.exists(poster_path):
                self.serve_static(poster_path)
            else:
                self.send_error(404, "Poster not found")
        elif path == "/api/poster_search":
            self.handle_api_poster_search(params)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        data = {}
        try:
            data = json.loads(body) if body else {}
        except Exception:
            pass

        if path == "/api/heartbeat":
            global LAST_HEARTBEAT, HEARTBEAT_ACTIVE
            LAST_HEARTBEAT = time.time()
            HEARTBEAT_ACTIVE = True
            cancel_shutdown()
            self.send_json({"status": "ok"})
            return
        elif path == "/api/browser_closing":
            log("🛑 [СЕРВЕР] Сигнал закрытия окна браузера получен...", "INFO")
            schedule_shutdown(3.5)
            self.send_json({"status": "closing"})
            return
        elif path == "/api/refresh":
            category = data.get("category", "movies")
            y_val = data.get("year", "2026")
            year = int(y_val) if str(y_val).isdigit() else 0
            log(f"🔄 [СКАНЕР] Пользователь запустил полное сканирование: [{category}] (год: {year})", "INFO")
            threading.Thread(target=tracker_engine.scan_category, args=(category, year, 1), daemon=True).start()
            self.send_json({"status": "started", "category": category, "year": year})
        elif path == "/api/scan_more":
            category = data.get("category", "movies")
            y_val = data.get("year", "2026")
            year = int(y_val) if str(y_val).isdigit() else 0
            log(f"⚡ [АВТО-ПОДГРУЗКА] Сканирование следующей порции трекера [{category}] (год: {year})...", "INFO")
            threading.Thread(target=tracker_engine.scan_next_tracker_page, args=(category, year), daemon=True).start()
            self.send_json({"status": "scanning", "category": category, "year": year})
        elif path == "/api/watchlist/add":
            tid = data.get("torrent_id")
            if tid:
                database.add_to_watchlist(tid)
                rel = database.get_release_by_id(tid)
                t_name = rel.get("title_ru", tid) if rel else tid
                log(f"💚 [БУДУ СМОТРЕТЬ] Добавлено: «{t_name}»", "SUCCESS")
                self.send_json({"status": "ok", "torrent_id": tid})
            else:
                self.send_error(400, "Missing torrent_id")
        elif path == "/api/watchlist/remove":
            tid = data.get("torrent_id")
            if tid:
                database.remove_from_watchlist(tid)
                log(f"↩️ [БУДУ СМОТРЕТЬ] Удалено из списка: #{tid}", "INFO")
                self.send_json({"status": "ok", "torrent_id": tid})
            else:
                self.send_error(400, "Missing torrent_id")
        elif path == "/api/ignored/add":
            tid = data.get("torrent_id")
            if tid:
                rel = database.get_release_by_id(tid)
                t_name = rel.get("title_ru", tid) if rel else tid
                database.add_to_ignored(tid)
                log(f"🚫 [НЕ БУДУ СМОТРЕТЬ] «{t_name}» скрыт (кэш очищен, сохранена краткая инфо)", "INFO")
                self.send_json({"status": "ok", "torrent_id": tid})
            else:
                self.send_error(400, "Missing torrent_id")
        elif path == "/api/ignored/restore":
            tid = data.get("torrent_id")
            if tid:
                database.restore_from_ignored(tid)
                log(f"↩️ [РАДАР] Фильм #{tid} возвращён из чёрного списка", "SUCCESS")
                self.send_json({"status": "ok", "torrent_id": tid})
            else:
                self.send_error(400, "Missing torrent_id")
        else:
            self.send_error(404, "Not Found")

    def handle_api_series_season_torrents(self, params):
        title = params.get("title", [""])[0].strip()
        season_str = params.get("season", ["1"])[0].strip()
        is_pack = season_str in ("pack", "packs", "multi")
        season = int(season_str) if season_str.isdigit() else (0 if is_pack else 1)
        title_en = params.get("title_en", [""])[0].strip()
        category = params.get("category", ["series"])[0].strip() or "series"
        
        releases = database.query_season_releases(title, season, category=category, is_pack=is_pack)
        
        # If fewer than 15 releases found in local DB, search on tracker on-demand for full series
        if len(releases) < 15 and title:
            clean_q = re.sub(r'[\'\"`’:\(\)\[\],.]', ' ', title).strip()
            clean_q = re.sub(r'\s+', ' ', clean_q)
            log(f"🔍 [СЕЗОНЫ] Поиск всех раздач сериала на трекере: «{clean_q}» в [{category}]...", "INFO")
            tracker_engine.search_tracker_by_query(clean_q, category)
            if title_en and len(title_en) > 2:
                clean_en = re.sub(r'[\'\"`’:\(\)\[\],.]', ' ', title_en).strip()
                clean_en = re.sub(r'\s+', ' ', clean_en)
                tracker_engine.search_tracker_by_query(clean_en, category)
            releases = database.query_season_releases(title, season, category=category, is_pack=is_pack)
            
        self.send_json({"items": releases, "season": season_str, "title": title, "is_pack": is_pack})

    def handle_api_items(self, params):
        category = params.get("category", ["movies"])[0]
        min_rating = float(params.get("min_rating", ["0.0"])[0])
        max_size = float(params.get("max_size", ["999.0"])[0])
        genre = params.get("genre", ["all"])[0]
        year = params.get("year", ["all"])[0]
        search = params.get("search", [""])[0]
        page = int(params.get("page", ["1"])[0])
        limit = int(params.get("limit", ["15"])[0])
        origin = params.get("origin", ["foreign"])[0]
        qualities = params.get("quality", None)
        if qualities:
            qualities = qualities[0].split(",") if isinstance(qualities[0], str) else qualities

        streaming = params.get("streaming", ["all"])[0]
        voiceover = params.get("voiceover", ["all"])[0]
        ongoing = params.get("ongoing", ["all"])[0]
        has_subtitles = params.get("has_subtitles", ["false"])[0].lower() in ("true", "1", "yes")
        anime_type = params.get("anime_type", ["all"])[0]
        repack_author = params.get("repack_author", ["all"])[0]
        release_format = params.get("release_format", ["all"])[0]
        crack_status = params.get("crack_status", ["all"])[0]
        software_category = params.get("software_category", ["all"])[0]

        if year == "all":
            y_desc = "все годы"
        elif str(year).strip().lower() in ("< 2000", "<2000", "pre2000", "old"):
            y_desc = "до 2000 года"
        else:
            y_desc = f"{year} г."
        q_desc = ",".join(qualities) if qualities else "любое"
        log(f"📡 [РАДАР] Запрос витрины [{category}], {y_desc}, происхождение: {origin}, жанр: {genre}, рейтинг: >={min_rating}, качество: {q_desc}, стр. {page}", "INFO")

        # If user is searching by title/query, perform deep search on tracker archive if fewer than 15 local items
        if search and search.strip():
            local_matches = database.query_releases(category=category, search=search, limit=15, origin=origin)
            if local_matches['total'] < 15:
                tracker_engine.search_tracker_by_query(search, category)

        data = database.query_releases(
            category=category, min_rating=min_rating,
            max_size=max_size, qualities=qualities, genre=genre,
            year=year, search=search, page=page, limit=limit,
            deduplicate=True, origin=origin,
            streaming=streaming, voiceover=voiceover, ongoing=ongoing,
            has_subtitles=has_subtitles, anime_type=anime_type,
            repack_author=repack_author, release_format=release_format,
            crack_status=crack_status, software_category=software_category
        )

        y_scan = int(year) if str(year).isdigit() else 0

        # Initial crawl only if category has 0 items in database
        if data["total"] == 0 and not search and page == 1:
            log(f"📡 [РАДАР] Каталог [{category}] пуст. Запуск первичного сканирования...", "INFO")
            tracker_engine.scan_category(category, y_scan, 1)
            data = database.query_releases(
                category=category, min_rating=min_rating,
                max_size=max_size, qualities=qualities, genre=genre,
                year=year, search=search, page=page, limit=limit,
                deduplicate=True, origin=origin,
                streaming=streaming, voiceover=voiceover, ongoing=ongoing,
                has_subtitles=has_subtitles, anime_type=anime_type,
                repack_author=repack_author, release_format=release_format,
                crack_status=crack_status, software_category=software_category
            )

        needs_fill = False
        if not search and len(data["items"]) < limit:
            needs_fill = True
            start_background_fill(category, y_scan, genre)

        data["needs_fill"] = needs_fill

        # Honest pagination
        if data["total"] <= limit:
            data["pages"] = 1
        else:
            data["pages"] = max(1, (data["total"] + limit - 1) // limit)
            if not search and len(data["items"]) >= limit and page >= data["pages"]:
                data["pages"] = page + 1

        log(f"✅ [РАДАР] Итого: {data['total']} релизов (выведено {len(data['items'])} на стр. {page})", "SUCCESS")
        self.send_json(data)

    def handle_api_items_poll(self, params):
        category = params.get("category", ["movies"])[0]
        min_rating = float(params.get("min_rating", ["0.0"])[0])
        max_size = float(params.get("max_size", ["999.0"])[0])
        genre = params.get("genre", ["all"])[0]
        year = params.get("year", ["all"])[0]
        search = params.get("search", [""])[0]
        page = int(params.get("page", ["1"])[0])
        limit = int(params.get("limit", ["15"])[0])
        origin = params.get("origin", ["foreign"])[0]
        qualities = params.get("quality", None)
        if qualities:
            qualities = qualities[0].split(",") if isinstance(qualities[0], str) else qualities

        streaming = params.get("streaming", ["all"])[0]
        voiceover = params.get("voiceover", ["all"])[0]
        ongoing = params.get("ongoing", ["all"])[0]
        has_subtitles = params.get("has_subtitles", ["false"])[0].lower() in ("true", "1", "yes")
        anime_type = params.get("anime_type", ["all"])[0]
        repack_author = params.get("repack_author", ["all"])[0]
        release_format = params.get("release_format", ["all"])[0]
        crack_status = params.get("crack_status", ["all"])[0]
        software_category = params.get("software_category", ["all"])[0]

        existing_raw = params.get("existing_ids", [""])[0]
        existing_ids = set([x.strip() for x in existing_raw.split(",") if x.strip()])

        poll_limit = max(limit * 2, 30)
        data = database.query_releases(
            category=category, min_rating=min_rating,
            max_size=max_size, qualities=qualities, genre=genre,
            year=year, search=search, page=page, limit=poll_limit,
            deduplicate=True, origin=origin,
            streaming=streaming, voiceover=voiceover, ongoing=ongoing,
            has_subtitles=has_subtitles, anime_type=anime_type,
            repack_author=repack_author, release_format=release_format,
            crack_status=crack_status, software_category=software_category
        )

        new_items = [it for it in data["items"] if str(it["torrent_id"]) not in existing_ids]

        with CRAWL_LOCK:
            t = ACTIVE_CRAWLS.get(category)
            is_running = t.is_alive() if t else False

        needed = max(0, limit - len(existing_ids))
        to_return = new_items[:needed]
        is_done = (len(existing_ids) + len(to_return) >= limit) or (not is_running and len(to_return) == 0)

        total_pages = 1 if data["total"] <= limit else max(1, (data["total"] + limit - 1) // limit)

        self.send_json({
            "new_items": to_return,
            "total": data["total"],
            "pages": total_pages,
            "done": is_done
        })

    def handle_api_years(self, params):
        category = params.get("category", ["movies"])[0]
        years = database.get_distinct_years(category)
        self.send_json({"years": years})

    def handle_api_genres(self, params):
        category = params.get("category", ["movies"])[0]
        genres = database.get_distinct_genres(category)
        self.send_json({"genres": genres})

    def handle_api_item(self, params):
        try:
            item_id = params.get("id", [""])[0]
            if not item_id:
                self.send_json({"error": "Missing id parameter"})
                return

            category = params.get("category", [None])[0]
            item = database.get_release_by_id(item_id, category=category)
            if not item:
                try:
                    tid_int = int(item_id)
                    details = tracker_engine.parse_full_details(tid_int)
                    if details:
                        item = details
                except Exception:
                    pass

            if not item:
                self.send_json({"error": "Item not found"})
                return

            log(f"🎬 [ОТКРЫТИЕ КАРТОЧКИ] #{item_id} «{item.get('title_ru')}» | {item.get('category')} | {item.get('quality')}", "INFO")

            if not item.get("description") and not item.get("audio_info") and not item.get("system_reqs"):
                details = tracker_engine.parse_full_details(item.get("torrent_id"))
                if details:
                    item = details

            self.send_json(item)
        except Exception as e:
            log(f"⚠️ Ошибка открытия карточки #{params.get('id', [''])[0]}: {e}", "ERROR")
            self.send_json({"error": str(e)})

    def handle_api_cards_status(self, params):
        try:
            raw_ids = params.get("ids", [""])[0]
            if not raw_ids:
                self.send_json({"items": []})
                return
            tids = [i.strip() for i in raw_ids.split(",") if i.strip()]
            if not tids:
                self.send_json({"items": []})
                return
            category = params.get("category", ["movies"])[0]
            conn = database.get_connection(category)
            c = conn.cursor()
            placeholders = ",".join(["?"] * len(tids))
            c.execute(f"""
                SELECT torrent_id, category, title, title_ru, title_en, year, poster_url, kp_rating, imdb_rating, shikimori_rating, mal_rating,
                       metacritic_critic, metacritic_user, opencritic_rating, genre, country, quality,
                       release_format, repack_author, app_version, is_ongoing, anime_type,
                       seasons_count, date_added
                FROM releases
                WHERE torrent_id IN ({placeholders})
            """, tids)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()

            # Trigger background preloading for missing posters
            for r in rows:
                tid = str(r.get("torrent_id"))
                p_url = r.get("poster_url")
                local_jpg = os.path.join(database.POSTERS_DIR, f"{tid}.jpg")
                if not p_url or not os.path.exists(local_jpg):
                    queue_poster_preload(
                        tid, category,
                        title=r.get("title_ru") or r.get("title") or "",
                        year=r.get("year") or 0,
                        title_en=r.get("title_en") or ""
                    )

            self.send_json({"items": rows})
        except Exception as e:
            self.send_json({"items": [], "error": str(e)})

    def handle_api_poster_search(self, params):
        title = params.get("title", [""])[0]
        year_str = params.get("year", ["0"])[0]
        year = int(year_str) if str(year_str).isdigit() else 0
        original_title = params.get("original_title", [""])[0]
        torrent_id = params.get("torrent_id", [""])[0]

        poster_url = tracker_engine.fetch_web_poster(title, year, original_title)
        if poster_url and torrent_id:
            local_url = tracker_engine.cache_poster_locally(torrent_id, poster_url)
            database.update_release_poster(torrent_id, local_url or poster_url)
            self.send_json({"poster_url": local_url or poster_url})
            return

        self.send_json({"poster_url": poster_url or ""})

    def serve_file(self, full_path, content_type):
        if not os.path.exists(full_path):
            self.send_error(404, "File not found")
            return
        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error reading file {full_path}: {e}")
            self.send_error(500, "Internal Server Error")

    def serve_static(self, file_path):
        if not os.path.exists(file_path):
            self.send_error(404, "Static file not found")
            return
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"
        self.serve_file(file_path, mime_type)

    def send_json(self, data):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass

def run_server(port=PORT):
    server = ThreadedHTTPServer(("127.0.0.1", port), RadarRequestHandler)
    log(f"============================================================", "SUCCESS")
    log(f" RADAR Server запущен на http://127.0.0.1:{port}", "SUCCESS")
    log(f"============================================================", "SUCCESS")
    
    # Auto-fix existing countries in background (instant local DB update)
    threading.Thread(target=tracker_engine.fix_existing_countries_in_db, daemon=True).start()

    # Strict On-Demand: Background downloading of unviewed posters/ratings is disabled!
    # Posters and ratings are loaded strictly for the 15 cards currently viewed on screen.

    # Watchdog monitor: stops server when browser closes
    threading.Thread(target=watchdog_monitor, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Остановка сервера RADAR...", "INFO")
        server.server_close()

if __name__ == "__main__":
    run_server()
