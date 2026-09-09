from __future__ import annotations

from backend.services.monitoring import _before_send


def test_monitoring_scrubs_credentials_and_business_request_data():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "s2_session=secret",
                "X-Client-Id": "client-42",
                "Content-Type": "application/json",
            },
            "cookies": {"s2_session": "secret"},
            "data": {"password": "secret"},
            "query_string": "token=secret",
        },
        "user": {"email": "user@example.com"},
    }

    sanitized = _before_send(event, {})

    assert sanitized["request"]["headers"]["Authorization"] == "[Filtered]"
    assert sanitized["request"]["headers"]["Cookie"] == "[Filtered]"
    assert sanitized["request"]["headers"]["X-Client-Id"] == "[Filtered]"
    assert sanitized["request"]["headers"]["Content-Type"] == "application/json"
    assert "cookies" not in sanitized["request"]
    assert "data" not in sanitized["request"]
    assert "query_string" not in sanitized["request"]
    assert "user" not in sanitized
