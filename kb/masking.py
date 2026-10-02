import re
from kb.config import CFG

_PATTERNS = [re.compile(p) for p in CFG.security.masking_patterns]

def mask(text: str) -> str:
    out = text or ""
    for p in _PATTERNS:
        out = p.sub("[REDACTED]", out)
    return out

def mask_hits(text: str) -> int:
    n = 0
    for p in _PATTERNS:
        n += len(p.findall(text or ""))
    return n