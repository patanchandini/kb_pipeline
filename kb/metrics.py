from prometheus_client import Counter, Histogram, Gauge, start_http_server
from kb.config import CFG

REQUESTS = Counter("kb_requests_total", "Total requests", ["endpoint", "status"])
LATENCY = Histogram("kb_request_latency_seconds", "Latency", ["endpoint"])
FAILURES = Counter("kb_failures_total", "Failures", ["stage"])
CONFIDENCE = Histogram("kb_confidence", "Answer confidence", buckets=[0.1,0.3,0.5,0.7,0.9,1.0])
ESCALATIONS = Counter("kb_escalations_total", "Escalated chats")
KB_VERSION = Gauge("kb_active_version", "Active KB version")
INJECTION_BLOCKED = Counter("kb_injection_blocked_total", "Blocked prompt injections")
MASKED = Counter("kb_masked_pii_total", "Redacted PII occurrences")

def serve_metrics():
    start_http_server(CFG.metrics.port)