import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.timex import timex_constants as CONSTANTS
from hummingbot.connector.exchange.timex import timex_web_utils as web_utils
from hummingbot.connector.exchange.timex.timex_order_book import TimexOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.timex.timex_exchange import TimexExchange


class TimexAPIOrderBookDataSource(OrderBookTrackerDataSource):
    HEARTBEAT_TIME_INTERVAL = 30.0

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 trading_pairs: List[str],
                 connector: 'TimexExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__(trading_pairs)
        self._connector = connector
        self._api_factory = api_factory

        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def get_last_traded_prices(self,
                                     trading_pairs: List[str],
                                     domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.
        :param trading_pair: the trading pair for which the order book will be retrieved
        :return: the response from the exchange (JSON dictionary)
        """
        params = {
            "market": await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
            "limit": "1000"
        }
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(endpoint=CONSTANTS.ORDER_BOOK_PATH_URL),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDER_BOOK_PATH_URL,
        )
        return data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        :param ws: the websocket assistant used to connect to the exchange
        """
        try:
            for trading_pair in self._trading_pairs:
                base, quote = trading_pair.split("-")
                await ws.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/trade.symbols/{base}/{quote}"
                    })
                )
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                await ws.send(
                    WSJSONRequest(payload={
                        "type": "SUBSCRIBE",
                        "requestId": f"{time.time_ns()}",
                        "pattern": f"/orderbook.raw/{symbol}"
                    })
                )
            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL,
                         ping_timeout=self.HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = TimexOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        base = raw_message["event"]["data"]["baseTokenSymbol"]
        quote = raw_message["event"]["data"]["quoteTokenSymbol"]
        trading_pair = f"{base}-{quote}"
        trade_message = TimexOrderBook.trade_message_from_exchange(raw_message, {"trading_pair": trading_pair})
        message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        # TimeX API doesn't provide diffs
        pass

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        event_type = event_message["event"]["type"]
        channel = {
            "RAW_ORDER_BOOK_UPDATED": self._snapshot_messages_queue_key,
            "TRADE": self._trade_messages_queue_key
        }[event_type]
        return channel
