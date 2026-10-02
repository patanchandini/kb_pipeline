import os, shutil, json, logging
from kb.config import CFG

log = logging.getLogger("validate")
MAX_BYTES = 5 * 1024 * 1024
MIN_BYTES = 10

def validate_file(path):
    if not os.path.isfile(path):
        return False, "not_a_file"
    size = os.path.getsize(path)
    if size < MIN_BYTES: return False, f"too_small({size})"
    if size > MAX_BYTES: return False, f"too_large({size})"
    if path.endswith(".json"):
        try:
            with open(path) as f: json.load(f)
        except Exception as e:
            return False, f"bad_json: {e}"
    else:
        try:
            with open(path, encoding="utf-8") as f:
                data = f.read()
            if not data.strip(): return False, "empty"
        except UnicodeDecodeError:
            return False, "encoding"
    return True, None

def quarantine(path, reason):
    os.makedirs(CFG.paths.quarantine_dir, exist_ok=True)
    base = os.path.basename(path)
    dest = os.path.join(CFG.paths.quarantine_dir, base)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(CFG.paths.quarantine_dir, f"{i}_{base}")
        i += 1
    shutil.move(path, dest)
    with open(dest + ".reason", "w") as f:
        f.write(reason)
    log.warning("Quarantined %s → %s (%s)", path, dest, reason)