"""Single wrapper for every outbound HTTP call the backend makes.

All outbound traffic (currently: Ollama) must go through `outbound_request()`
so that host-allowlist enforcement and rejection counting happen in exactly
one place. This is what the Privacy page reports as a *measured* number
rather than a declared one, per the customer-isolation constraint.
"""
import logging
from urllib.parse import urlparse

import httpx

from app.config import get_settings

logger = logging.getLogger("buildgate.outbound")


class OutboundHostNotAllowedError(Exception):
    def __init__(self, host: str):
        self.host = host
        super().__init__(f"Outbound host '{host}' is not in the allowlist")


class _OutboundCounters:
    def __init__(self) -> None:
        self.allowed = 0
        self.rejected = 0

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "rejected": self.rejected}


counters = _OutboundCounters()


def _is_allowed(host: str) -> bool:
    settings = get_settings()
    return host.lower() in settings.outbound_allowed_hosts_list


def outbound_request(method: str, url: str, **kwargs) -> httpx.Response:
    host = urlparse(url).hostname or ""

    if not _is_allowed(host):
        counters.rejected += 1
        logger.warning("Rejected outbound request to disallowed host: %s", host)
        raise OutboundHostNotAllowedError(host)

    counters.allowed += 1
    timeout = kwargs.pop("timeout", 30.0)
    with httpx.Client(timeout=timeout) as client:
        return client.request(method, url, **kwargs)
