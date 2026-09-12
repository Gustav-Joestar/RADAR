import json
import mimetypes
import os
import sys
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

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

def do_shutdown():
    log("🛑 [СЕРВЕР] Окно браузера закрыто пользователем. Остановка процесса RADAR...", "INFO")
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
            log("🛑 [СЕРВЕР] Потеряна связь с окном браузера (>120 сек). Остановка сервера RADAR...", "INFO")
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
        elif path == "/api/item":
            self.handle_api_item(params)
        elif path == "/api/watchlist":
            search = params.get("search", [""])[0]
            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["15"])[0])
            self.send_json(database.query_watchlist(search=search, page=page, limit=limit))
        elif path == "/api/ignored":
            search = params.get("search", [""])[0]
            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["15"])[0])
            self.send_json(database.query_ignored(search=search, page=page, limit=limit))
        elif path == "/api/counts":
            self.send_json(database.get_curation_counts())
        elif path == "/api/logs":
            self.send_json({"logs": get_logs()})
        elif path == "/api/genres":
            self.handle_api_genres(params)
        elif path == "/api/years":
            self.handle_api_years(params)
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
        if year == "all":
            y_desc = "все годы"
        elif str(year).strip().lower() in ("< 2000", "<2000", "pre2000", "old"):
            y_desc = "до 2000 года"
        else:
            y_desc = f"{year} г."
        q_desc = ",".join(qualities) if qualities else "любое"
        log(f"📡 [РАДАР] Запрос витрины [{category}], {y_desc}, происхождение: {origin}, жанр: {genre}, рейтинг: >={min_rating}, качество: {q_desc}, стр. {page}", "INFO")

        # If user is searching by title/query, perform deep search on tracker archive
        if search and search.strip():
            local_matches = database.query_releases(category=category, search=search, limit=1, origin=origin)
            if local_matches['total'] < 3:
                tracker_engine.search_tracker_by_query(search, category)

        data = database.query_releases(
            category=category, min_rating=min_rating,
            max_size=max_size, qualities=qualities, genre=genre,
            year=year, search=search, page=page, limit=limit,
            deduplicate=True, origin=origin
        )

        # Initial crawl only if category has 0 items in database
        if data["total"] == 0 and not search and page == 1:
            y_scan = int(year) if str(year).isdigit() else 0
            log(f"📡 [РАДАР] Каталог [{category}] пуст. Запуск первичного сканирования...", "INFO")
            tracker_engine.scan_category(category, y_scan, 1)
            data = database.query_releases(
                category=category, min_rating=min_rating,
                max_size=max_size, qualities=qualities, genre=genre,
                year=year, search=search, page=page, limit=limit,
                deduplicate=True, origin=origin
            )

        # Ensure page 1 has all posters loaded immediately so user sees complete cards
        if page == 1 and not search:
            missing_ids = [it["torrent_id"] for it in data["items"] if not it.get("poster_url")]
            if missing_ids:
                from concurrent.futures import ThreadPoolExecutor
                log(f"⚡ [ПОСТЕРЫ] Мгновенная дозагрузка {len(missing_ids)} обложек для витрины...", "INFO")
                with ThreadPoolExecutor(max_workers=5) as executor:
                    list(executor.map(tracker_engine.parse_full_details, missing_ids))
                data = database.query_releases(
                    category=category, min_rating=min_rating,
                    max_size=max_size, qualities=qualities, genre=genre,
                    year=year, search=search, page=page, limit=limit,
                    deduplicate=True, origin=origin
                )
        elif page > 1:
            missing_ids = [it["torrent_id"] for it in data["items"] if not it.get("poster_url")]
            if missing_ids:
                threading.Thread(target=lambda ids: [tracker_engine.parse_full_details(tid) for tid in ids], args=(missing_ids,), daemon=True).start()

        log(f"✅ [РАДАР] Итого: {data['total']} релизов (выведено {len(data['items'])} на стр. {page})", "SUCCESS")
        self.send_json(data)

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
                self.send_error(400, "Missing id parameter")
                return

            item = database.get_release_by_id(item_id)
            if not item:
                self.send_error(404, "Item not found")
                return

            log(f"🎬 [ОТКРЫТИЕ КАРТОЧКИ] #{item_id} «{item.get('title_ru')}» | {item.get('quality')} | КП: {item.get('kp_rating') or '—'} | IMDb: {item.get('imdb_rating') or '—'}", "INFO")

            if not item.get("description") and not item.get("audio_info"):
                details = tracker_engine.parse_full_details(item.get("torrent_id"))
                if details:
                    item = details

            self.send_json(item)
        except Exception as e:
            log(f"⚠️ Ошибка открытия карточки #{params.get('id', [''])[0]}: {e}", "ERROR")
            self.send_json({"error": str(e)})

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
            self.send_error(500, f"Error reading file: {e}")

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

    # Auto-scan initial 'movies' category only if database is fresh (1 page, first 15 with covers immediately)
    count = database.query_releases(category="movies", days=0, max_size=0, min_rating=0, year="all")["total"]
    if count == 0:
        log("🚀 [СТАРТ] Первичная загрузка 15 фильмов с обложками...", "INFO")
        threading.Thread(target=tracker_engine.scan_category, args=("movies", 2026, 1), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Остановка сервера RADAR...", "INFO")
        server.server_close()

if __name__ == "__main__":
    run_server()
