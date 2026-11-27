"""Upload B2 không còn treo 60 s/lần (job 46: 182 s cho 1 chunk 7 MB)."""

from app import storage
from app.config import settings


def test_b2_client_uses_short_timeouts_and_standard_retries():
    cfg = storage._client_config()
    assert cfg.connect_timeout == settings.b2_connect_timeout_sec == 10.0
    assert cfg.read_timeout == settings.b2_read_timeout_sec == 30.0
    assert cfg.retries == {"max_attempts": 5, "mode": "standard"}
