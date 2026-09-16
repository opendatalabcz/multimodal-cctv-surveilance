"""HTTP GET with a TLS fallback for hosts that present a broken chain."""

from __future__ import annotations

import requests
from requests.exceptions import SSLError
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def get_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    """GET ``url``, retrying once with ``verify=False`` on certificate errors.

    Prague municipal cameras (``bezpecnost.praha.eu``) currently serve a
    self-signed certificate in the chain, which fails ``certifi`` verification.
    """
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except SSLError:
        return requests.get(url, headers=headers, timeout=timeout, verify=False)
