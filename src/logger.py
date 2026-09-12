import time
from collections import deque
import sys

# Set UTF-8 encoding for standard streams on Windows if possible
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Maintain circular buffer of the last 200 log entries
LOG_HISTORY = deque(maxlen=200)

def log(msg, level="INFO"):
    timestamp = time.strftime("%H:%M:%S")
    entry = {
        "time": timestamp,
        "msg": str(msg),
        "level": level
    }
    LOG_HISTORY.append(entry)
    
    try:
        prefix = f"[{timestamp}] [{level}]"
        safe_msg = str(msg)
        print(f"{prefix} {safe_msg}")
        sys.stdout.flush()
    except Exception:
        try:
            enc = sys.stdout.encoding or 'cp1251'
            clean = safe_msg.encode(enc, errors='replace').decode(enc, errors='replace')
            print(f"[{timestamp}] [{level}] {clean}")
        except Exception:
            pass

def get_logs():
    return list(LOG_HISTORY)
