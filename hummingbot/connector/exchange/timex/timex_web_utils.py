import time
from typing import Optional

import hummingbot.connector.exchange.timex.timex_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


def public_rest_url(endpoint: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for provided public REST endpoint

    :param endpoint: a public REST endpoint
    :param domain: unused

    :return: the full URL to the endpoint
    """
    if CONSTANTS.REST_URL[-1] != "/" and endpoint[0] != "/":
        endpoint = "/" + endpoint
    return CONSTANTS.REST_URL + endpoint


def private_rest_url(endpoint: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    return public_rest_url(endpoint, domain)


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    auth: Optional[AuthBase] = None
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth)
    return api_factory


def create_throttler() -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)


async def get_current_server_time(
    throttler: Optional[AsyncThrottler] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> float:
    return time.time()
