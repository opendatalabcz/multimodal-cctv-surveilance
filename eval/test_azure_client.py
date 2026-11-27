"""Checks retry handling without making provider requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock, patch

from eval.azure_client import AzureVisionClient, _retry_after_seconds, _retry_delay


def test_retry_after_parses_seconds_and_http_dates() -> None:
    now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    retry_date = format_datetime(now + timedelta(seconds=12), usegmt=True)
    past_date = format_datetime(now - timedelta(seconds=12), usegmt=True)

    assert _retry_after_seconds("3", now=now) == 3
    assert _retry_after_seconds(retry_date, now=now) == 12
    assert _retry_after_seconds(past_date, now=now) == 0
    assert _retry_after_seconds("not-a-date", now=now) is None
    assert _retry_after_seconds("inf", now=now) is None


def test_retry_delay_uses_server_delay_or_jittered_backoff() -> None:
    with patch("eval.azure_client.random.uniform", return_value=0.25) as uniform:
        assert _retry_delay(3.0, 2.0) == 3.25
        assert _retry_delay(None, 2.0) == 0.25
    assert uniform.call_count == 2


def test_post_honors_retry_after_before_retrying() -> None:
    client = object.__new__(AzureVisionClient)
    client.timeout_s = 5
    limited = Mock(status_code=429, text="rate limited", headers={"Retry-After": "3"})
    success = Mock(status_code=200, ok=True)
    success.json.return_value = {"ok": True}

    with (
        patch("eval.azure_client.requests.post", side_effect=[limited, success]) as post,
        patch("eval.azure_client.time.sleep") as sleep,
        patch("eval.azure_client.random.uniform", return_value=0.5),
    ):
        body, error = client._post("https://example.invalid", {}, {})

    assert body == {"ok": True}
    assert error is None
    assert post.call_count == 2
    sleep.assert_called_once_with(3.5)


if __name__ == "__main__":
    test_retry_after_parses_seconds_and_http_dates()
    test_retry_delay_uses_server_delay_or_jittered_backoff()
    test_post_honors_retry_after_before_retrying()
    print("retry checks passed")
