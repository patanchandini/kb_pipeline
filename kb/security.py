import re
from functools import wraps
from fastapi import Header, HTTPException
from kb.config import CFG

ROLE_ORDER = {"viewer": 1, "editor": 2, "admin": 3}

def _key_to_role(api_key: str):
    api_keys = CFG.security.api_keys
    # Handle both dict and _NS forms
    items = api_keys.items() if hasattr(api_keys, "items") else vars(api_keys).items()
    for role, key in items:
        if api_key == key:
            return role
    return None

def require_role(minimum: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, x_api_key: str = Header(None), **kwargs):
            role = _key_to_role(x_api_key or "")
            if not role or ROLE_ORDER[role] < ROLE_ORDER[minimum]:
                raise HTTPException(status_code=403, detail="forbidden")
            return fn(*args, **kwargs)
        return wrapper
    return deco

_INJ = [re.compile(p, re.I) for p in CFG.security.injection_patterns]

def scan_injection(text: str):
    """Return (is_unsafe, matched_pattern)."""
    for p in _INJ:
        if p.search(text or ""):
            return True, p.pattern
    return False, None