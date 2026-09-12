import os
import sys
import time
import urllib.request
import webbrowser
import subprocess

PORT = 8765
URL = f"http://127.0.0.1:{PORT}"

def is_running():
    try:
        req = urllib.request.Request(f"{URL}/api/logs")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "server.py")
    
    if not is_running():
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.Popen([sys.executable, server_path], cwd=script_dir, creationflags=flags)
        
        for _ in range(25):
            time.sleep(0.2)
            if is_running():
                break

    webbrowser.open(URL)

if __name__ == "__main__":
    main()
