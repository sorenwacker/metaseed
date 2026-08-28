"""Push and pull datasets and profiles between this instance and a metaseed-hub.

The hub is the shared, deployed service; this instance is one person's. The
exchange is explicit — a push or a pull the user chooses — and never
overwrites without being told to. Requires the ``metaseed[hub]`` extra.
"""

from metaseed.connection import ConnectionCheck
from metaseed.hub.client import HubApiError, HubClient, client_from_settings
from metaseed.hub.connection import check_connection

__all__ = [
    "ConnectionCheck",
    "HubApiError",
    "HubClient",
    "check_connection",
    "client_from_settings",
]
