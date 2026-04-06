import sys
import os
from pathlib import Path

# Ensure backend/ is on sys.path so tests can import backend modules directly
_backend = Path(__file__).parent.parent / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as requiring live API keys (deselect with -m 'not integration')"
    )


@pytest.fixture
def groq_client():
    """Real Groq client for integration tests"""
    from groq import AsyncGroq
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping integration test")
    return AsyncGroq(api_key=api_key)


@pytest.fixture
def sample_fresh_news():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    return [
        {
            "headline": "China widens ban on BHP iron ore",
            "event_date": (now - timedelta(days=8)).strftime("%Y-%m-%d"),
            "category": "Strategic developments"
        },
        {
            "headline": "Iron ore futures stable",
            "event_date": (now - timedelta(days=2)).strftime("%Y-%m-%d"),
            "category": "Strategic developments"
        }
    ]
