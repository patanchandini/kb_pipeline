import yaml
import os
from typing import Any, Dict


class _NS:
    """Namespace wrapper — only top-level sections."""
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)   # keep nested dicts as plain dicts


class Config:
    def __init__(self, path="config.yaml"):
        with open(path) as f:
            self.raw: Dict[str, Any] = yaml.safe_load(f)
        for k, v in self.raw.items():
            setattr(self, k, v if not isinstance(v, dict) else _NS(v))


CFG = Config(os.environ.get("KB_CONFIG", "config.yaml"))