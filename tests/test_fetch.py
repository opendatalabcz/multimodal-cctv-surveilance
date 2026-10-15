from unittest.mock import MagicMock, patch

import requests

from cctv.fetch.http import get_url


def test_get_url_retries_without_verify_on_ssl_error() -> None:
    ok = MagicMock()
    ok.status_code = 200

    def fake_get(url, headers=None, timeout=None, verify=True):
        if verify is True:
            raise requests.exceptions.SSLError("self-signed certificate in certificate chain")
        return ok

    with patch("cctv.fetch.http.requests.get", side_effect=fake_get):
        response = get_url("https://bezpecnost.praha.eu/cameras/1/image")

    assert response is ok
