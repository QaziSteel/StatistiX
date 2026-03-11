import os
import requests

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

def log_event(event_type: str, payload: dict):
    """Send a JSON payload to an n8n webhook (if configured)."""
    if not N8N_WEBHOOK_URL:
        return
    try:
        data = {"event": event_type, "payload": payload}
        requests.post(N8N_WEBHOOK_URL, json=data, timeout=5)
    except Exception:
        pass
