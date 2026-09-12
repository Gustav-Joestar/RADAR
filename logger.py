import time
from collections import deque
import sys

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
    
    # Print to console with colored indicator
    prefix = f"[{timestamp}] [{level}]"
    print(f"{prefix} {msg}")
    sys.stdout.flush()

def get_logs():
    return list(LOG_HISTORY)
