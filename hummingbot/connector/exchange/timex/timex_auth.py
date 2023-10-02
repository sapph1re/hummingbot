import base64
from typing import Dict

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class TimexAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, id_address: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.id_address = id_address
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.header_for_authentication())
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. TimeX does not use this
        functionality
        """
        return request  # pass-through

    def header_for_authentication(self) -> Dict[str, str]:
        auth = "Basic " + base64.b64encode(f"{self.api_key}:{self.secret_key}".encode("utf-8")).decode("utf-8")
        return {"Authorization": auth}
