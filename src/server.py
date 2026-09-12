import json
import mimetypes
import os
import sys
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import database
import tracker_engine
from logger import log, get_logs

PORT = 8765
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

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
        elif path == "/api/logs":
            self.send_json({"logs": get_logs()})
        elif path == "/api/genres":
            self.handle_api_genres(params)
        elif path == "/api/years":
            self.handle_api_years(params)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/refresh":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            category = "movies"
            year = 2026
            try:
                data = json.loads(body) if body else {}
                category = data.get("category", "movies")
                y_val = data.get("year", "2026")
                year = int(y_val) if str(y_val).isdigit() else 0
            except Exception:
                pass
            
            log(f"🔄 [СКАНЕР] Пользователь запустил сканирование: [{category}] (год: {year})", "INFO")
            threading.Thread(target=tracker_engine.scan_category, args=(category, year, 2), daemon=True).start()
            self.send_json({"status": "started", "category": category, "year": year})
        elif path == "/api/clear-cache":
            database.clear_cache()
            log("🗑️ [КЭШ] Пользователь полностью очистил локальную базу данных и кэш", "WARNING")
            self.send_json({"status": "cleared", "message": "Cache successfully cleared"})
        else:
            self.send_error(404, "Not Found")

    def handle_api_items(self, params):
        category = params.get("category", ["movies"])[0]
        days = int(params.get("days", ["7"])[0])
        min_rating = float(params.get("min_rating", ["0.0"])[0])
        max_size = float(params.get("max_size", ["15.0"])[0])
        genre = params.get("genre", ["all"])[0]
        year = params.get("year", ["2026"])[0]
        search = params.get("search", [""])[0]
        page = int(params.get("page", ["1"])[0])
        limit = int(params.get("limit", ["15"])[0])
        qualities = params.get("quality", None)
        if qualities:
            qualities = qualities[0].split(",") if isinstance(qualities[0], str) else qualities

        q_desc = ",".join(qualities) if qualities else "любое"
        log(f"📡 [РАДАР] Запрос витрины [{category}], {year} г., качество: {q_desc}, размер: <={max_size}GB, стр. {page}", "INFO")

        data = database.query_releases(
            category=category, days=days, min_rating=min_rating,
            max_size=max_size, qualities=qualities, genre=genre,
            year=year, search=search, page=page, limit=limit,
            deduplicate=True
        )

        log(f"✅ [РАДАР] Найдено {data['total']} релизов (выведено {len(data['items'])} на стр. {page})", "SUCCESS")

        # If 0 results with current strict filter, check if category is empty for this year
        if data["total"] == 0 and not search and genre == "all":
            count_all = database.query_releases(category=category, days=0, max_size=0, min_rating=0, year=year)["total"]
            if count_all == 0:
                y_scan = int(year) if str(year).isdigit() else 2026
                log(f"Категория [{category}] ({year}) пуста в базе. Запуск фонового сбора...", "INFO")
                threading.Thread(target=tracker_engine.scan_category, args=(category, y_scan, 2), daemon=True).start()

        # Auto-queue background details & poster fetch for any items on screen that lack posters
        missing_posters = [it.get("torrent_id") for it in data["items"] if not it.get("poster_url") and it.get("torrent_id")]
        if missing_posters:
            threading.Thread(target=lambda ids: [tracker_engine.parse_full_details(tid) for tid in ids], args=(missing_posters,), daemon=True).start()

        self.send_json(data)

    def handle_api_years(self, params):
        category = params.get("category", ["movies"])[0]
        years = database.get_distinct_years(category)
        self.send_json({"years": years})

    def handle_api_item(self, params):
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

    def handle_api_genres(self, params):
        category = params.get("category", ["movies"])[0]
        genres = database.get_distinct_genres(category)
        self.send_json({"genres": genres})

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
    
    # Auto-scan initial categories if database is fresh
    for cat in ["movies", "series", "anime", "games", "software"]:
        count = database.query_releases(category=cat, days=0, max_size=0, min_rating=0, year="all")["total"]
        if count == 0:
            y_scan = 2026 if cat in ("movies", "series", "anime") else 0
            threading.Thread(target=tracker_engine.scan_category, args=(cat, y_scan, 2), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Остановка сервера RADAR...", "INFO")
        server.server_close()

if __name__ == "__main__":
    run_server()
