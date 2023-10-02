import time
import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.timex import timex_constants as CONSTANTS
from hummingbot.connector.exchange.timex.timex_auth import TimexAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.timex.timex_exchange import TimexExchange


class TimexAPIUserStreamDataSource(UserStreamTrackerDataSource):

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: TimexAuth,
                 trading_pairs: List[str],
                 connector: 'TimexExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: TimexAuth = auth
        self._api_factory = api_factory
        self._trading_pairs: List[str] = trading_pairs
        self._connector = connector

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL, ping_timeout=CONSTANTS.PING_TIMEOUT)
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to order events, trades and balance updates.
        :param websocket_assistant: the websocket assistant used to connect to the exchange
        """
        try:
            # get all tokens from trading pairs
            tokens = set()
            for trading_pair in self._trading_pairs:
                base, quote = trading_pair.split("-")
                tokens.add(base)
                tokens.add(quote)
            # subscribe to user deposits & withdrawals
            for token in tokens:
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/deposit.symbols/{self._auth.id_address}/{token}"
                    })
                )
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/withdrawal.symbols/{self._auth.id_address}/{token}"
                    })
                )
            for trading_pair in self._trading_pairs:
                base, quote = trading_pair.split("-")
                fee_token = self._connector.trading_pair_fee_token(trading_pair)
                # subscribe to user order events
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/order.symbols/{self._auth.id_address}/{base}/{quote}/{fee_token}"
                    })
                )
                # and to order updates
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/order-update.symbols/{self._auth.id_address}/{base}/{quote}/{fee_token}"
                    })
                )
                # and to order expirations
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/order-expired.symbols/{self._auth.id_address}/{base}/{quote}/{fee_token}"
                    })
                )
                # and to market orders
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/market-order.symbols/{self._auth.id_address}/{base}/{quote}/{fee_token}"
                    })
                )
                # subscribe to user trades
                base_address = self._connector.token_address(base)
                quote_address = self._connector.token_address(quote)
                await websocket_assistant.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/trade.accounts/{self._auth.id_address}/{base_address}/{quote_address}"
                    })
                )
                self.logger().info("Subscribed to private order changes and balance updates channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error occurred subscribing to user streams...")
            raise

    async def _process_event_message(self, event_message: Dict[str, Any], queue: asyncio.Queue):
        if event_message.get("type") in ["DEPOSIT", "WITHDRAWAL", "ORDER", "ORDER_UPDATE", "ORDER_EXPIRED",
                                         "MARKET_ORDER", "TRADE"]:
            queue.put_nowait(event_message)
