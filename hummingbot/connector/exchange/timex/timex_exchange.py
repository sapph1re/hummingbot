import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.timex import (
    timex_constants as CONSTANTS,
    timex_utils as utils,
    timex_web_utils as web_utils,
)
from hummingbot.connector.exchange.timex.timex_api_order_book_data_source import TimexAPIOrderBookDataSource
from hummingbot.connector.exchange.timex.timex_api_user_stream_data_source import TimexAPIUserStreamDataSource
from hummingbot.connector.exchange.timex.timex_auth import TimexAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class TimexExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        timex_api_key: str,
        timex_api_secret: str,
        timex_id_address: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.api_key = timex_api_key
        self.secret_key = timex_api_secret
        self.id_address = timex_id_address
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs

        # some API endpoints require fee token specified, so we store it for every pair
        self._trading_pairs_fee_token = {}
        # some API endpoints require token address instead of symbol, so we map them
        self._token_addresses = {}

        super().__init__(client_config_map)

    @property
    def authenticator(self):
        return TimexAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            id_address=self.id_address,
            time_provider=self._time_synchronizer)

    @property
    def name(self) -> str:
        return "timex"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.TICKERS_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def trading_pair_fee_token(self, trading_pair: str):
        return self._trading_pairs_fee_token[trading_pair]

    def token_address(self, token: str):
        return self._token_addresses[token]

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        pairs_prices = await self._api_get(path_url=CONSTANTS.TICKERS_PATH_URL)
        return pairs_prices

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        # API does not seem to care about timestamps at all
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        # No such error in API
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        # No such error in API
        return False

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return TimexAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return TimexAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_NaN,
        is_maker: Optional[bool] = None
     ) -> TradeFeeBase:
        return build_trade_fee(
            exchange=self.name,
            is_maker=is_maker or order_type is OrderType.LIMIT_MAKER,
            base_currency=base_currency,
            quote_currency=quote_currency,
            order_type=order_type,
            order_side=order_side,
            amount=amount,
            price=price,
        )

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs
    ) -> Tuple[str, float]:
        amount_str = f"{amount:f}"
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side_str = 'BUY' if trade_type is TradeType.BUY else 'SELL'
        type_str = "MARKET" if order_type == OrderType.MARKET else "LIMIT"
        api_params = {
            "symbol": symbol,
            "side": side_str,
            "quantity": amount_str,
            "orderTypes": type_str,
            "clientOrderId": order_id
        }
        if order_type is OrderType.LIMIT:
            price_str = f"{price:f}"
            api_params["price"] = price_str
            api_params["expireIn"] = 60 * 60 * 24 * 365 * 10  # 10 years
        order_result = await self._api_post(
            path_url=CONSTANTS.ORDER_PATH_URL,
            data=api_params,
            is_auth_required=True,
        )
        return str(order_result["orders"][0]["id"]), self.current_timestamp

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        cancel_result = await self._api_delete(
            path_url=CONSTANTS.ORDER_PATH_URL,
            params={
                "id": order_id,
            },
            is_auth_required=True,
        )
        if 'error' not in cancel_result:
            return True
        return False

    async def _format_trading_rules(self, markets: List[Dict[str, Any]]) -> List[TradingRule]:
        trading_rules = []
        for market in markets:
            if utils.is_pair_information_valid(market):
                try:
                    trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=market.get("symbol"))
                    trading_rules.append(
                        TradingRule(
                            trading_pair=trading_pair,
                            min_order_size=Decimal(market["baseMinSize"]),
                            min_notional_size=Decimal(market["quoteMinSize"]),
                            min_price_increment=Decimal(market["tickSize"]),
                            min_base_amount_increment=Decimal(market["quantityIncrement"]),
                            min_order_value=Decimal(market["quantityIncrement"]),
                        )
                    )
                except Exception:
                    self.logger().exception(f"Error parsing the trading pair {market}. Skipping.")
        return trading_rules

    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        pass

    async def _get_trades(self, trading_pair: str) -> List[Dict[str, Any]]:
        """
        Get our trades for a trading pair

        Example:
        [{
            "id": 44773524,
            "timestamp": "2023-09-21T07:07:43.521164Z",
            "direction": "SELL",
            "price": "0.0089996",
            "quantity": "0.1",
            "feeQuantity": "0",
            "feeSymbol": "ETH",
            "ownerOrderId": "0x6eece2ae5c9543931df323ca094e757ca5059d5d3c2fe56fef14d2efa86fc204",
            "clientOrderId": "test005"
        }, ...]
        """
        trades = await self._api_get(
            path_url=CONSTANTS.TRADES_PATH_URL,
            params={
                "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
                "useCache": False,
            },
            is_auth_required=True,
            limit_id=CONSTANTS.TRADES_PATH_URL
        )
        return trades

    async def _process_trade_event(self, event: Dict[str, Any]):
        pair = combine_to_hb_trading_pair(base=event['data']['baseTokenSymbol'], quote=event['data']['quoteTokenSymbol'])
        # find the order
        order = None
        trade = None
        for t in await self._get_trades(pair):
            if t["id"] == event["data"]["id"]:
                order = self._order_tracker.fetch_order(exchange_order_id=t["ownerOrderId"])
                trade = t
                break
        if order is None:
            self.logger().warning(f"Trade message #{event['data']['id']}: trade not found")
            return
        # create the trade update
        fee = TradeFeeBase.new_spot_fee(
            fee_schema=self.trade_fee_schema(),
            trade_type=order.trade_type,
            percent_token=trade["feeSymbol"],
            flat_fees=[TokenAmount(
                amount=Decimal(trade["feeQuantity"]),
                token=trade["feeSymbol"]
            )]
        )
        trade_update = TradeUpdate(
            trade_id=str(trade["id"]),
            client_order_id=order.client_order_id,
            exchange_order_id=order.exchange_order_id,
            trading_pair=order.trading_pair,
            fee=fee,
            fill_base_amount=Decimal(trade["quantity"]),
            fill_quote_amount=Decimal(trade["quantity"]) * Decimal(trade["price"]),
            fill_price=Decimal(trade["price"]),
            fill_timestamp=utils.parse_timestamp(trade["timestamp"]),
        )
        self._order_tracker.process_trade_update(trade_update)

    async def _process_order_event(self, event: Dict[str, Any]):
        pair = combine_to_hb_trading_pair(base=event['data']['baseTokenSymbol'], quote=event['data']['quoteTokenSymbol'])
        order = self._order_tracker.fetch_order(exchange_order_id=event["reference"])
        # TODO: what's the order's state?
        state = self._normalise_order_message_state(event, order) or order.current_state
        order_update = OrderUpdate(
            trading_pair=order.trading_pair,
            update_timestamp=utils.parse_timestamp(event["timestamp"]),
            new_state=state,
            client_order_id=order.client_order_id,
            exchange_order_id=order.exchange_order_id,
        )
        self._order_tracker.process_order_update(order_update=order_update)

    def _normalise_order_message_state(self, order_msg: Dict[str, Any], tracked_order):
        state = None
        # we do not handle:
        #   "failed" because it is handled by create order
        #   "put" as the exchange order id is returned in the create order response
        #   "open" for same reason

        # same field for both WS and REST
        amount_left = Decimal(order_msg.get("left"))
        filled_amount = Decimal(order_msg.get("filled_total"))

        # WS
        if "event" in order_msg:
            event_type = order_msg.get("event")
            if event_type == "update":
                state = OrderState.FILLED
                if amount_left > 0:
                    state = OrderState.PARTIALLY_FILLED
            if event_type == "finish":
                finish_as = order_msg.get("finish_as")
                if finish_as == "filled" or finish_as == "ioc":
                    state = OrderState.FILLED
                elif finish_as == "cancelled":
                    state = OrderState.CANCELED
                elif finish_as == "open" and filled_amount > 0:
                    state = OrderState.PARTIALLY_FILLED
        else:
            status = order_msg.get("status")
            if status == "closed":
                finish_as = order_msg.get("finish_as")
                if finish_as == "filled" or finish_as == "ioc":
                    state = OrderState.FILLED
                elif finish_as == "cancelled":
                    state = OrderState.CANCELED
                elif finish_as == "open" and filled_amount > 0:
                    state = OrderState.PARTIALLY_FILLED
            if status == "cancelled":
                state = OrderState.CANCELED
        return state

    async def _user_stream_event_listener(self):
        """
        This functions runs in background continuously processing the events received from the exchange by the user
        stream data source. It keeps reading events from the queue until the task is interrupted.
        The events received are balance updates, order updates and trade events.
        """
        async for event in self._iter_user_event_queue():
            try:
                event_type = event.get("type")
                try:
                    if event_type == "TRADE":
                        await self._process_trade_event(event)
                    elif event_type in ["ORDER", "ORDER_UPDATE", "ORDER_EXPIRED", "MARKET_ORDER"]:
                        await self._process_order_event(event)
                    # TODO: "DEPOSIT", "WITHDRAWAL"

                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger().error(
                        "Unexpected error in user stream listener loop.", exc_info=True)
                    await self._sleep(5.0)

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            exchange_order_id = int(order.exchange_order_id)
            trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=order.trading_pair)
            all_fills_response = await self._api_get(
                path_url=CONSTANTS.MY_TRADES_PATH_URL,
                params={
                    "symbol": trading_pair,
                    "orderId": exchange_order_id
                },
                is_auth_required=True,
                limit_id=CONSTANTS.MY_TRADES_PATH_URL)

            for trade in all_fills_response:
                exchange_order_id = str(trade["orderId"])
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token=trade["commissionAsset"],
                    flat_fees=[TokenAmount(amount=Decimal(trade["commission"]), token=trade["commissionAsset"])]
                )
                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade["qty"]),
                    fill_quote_amount=Decimal(trade["quoteQty"]),
                    fill_price=Decimal(trade["price"]),
                    fill_timestamp=trade["time"] * 1e-3,
                )
                trade_updates.append(trade_update)

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=tracked_order.trading_pair)
        updated_order_data = await self._api_get(
            path_url=CONSTANTS.ORDER_PATH_URL,
            params={
                "symbol": trading_pair,
                "origClientOrderId": tracked_order.client_order_id},
            is_auth_required=True)

        new_state = CONSTANTS.ORDER_STATE[updated_order_data["status"]]

        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(updated_order_data["orderId"]),
            trading_pair=tracked_order.trading_pair,
            update_timestamp=updated_order_data["updateTime"] * 1e-3,
            new_state=new_state,
        )

        return order_update

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        account_info = await self._api_get(
            path_url=CONSTANTS.ACCOUNTS_PATH_URL,
            is_auth_required=True)

        balances = account_info["balances"]
        for balance_entry in balances:
            asset_name = balance_entry["asset"]
            free_balance = Decimal(balance_entry["free"])
            total_balance = Decimal(balance_entry["free"]) + Decimal(balance_entry["locked"])
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, markets: List[Dict[str, Any]]):
        # [{
        #     "alternativeCurrency": null,
        #     "alternativeTokenAddress": null,
        #     "baseCurrency": "EOS",
        #     "baseMinSize": "1",
        #     "baseTokenAddress": "0x3dc290b60a1a11b1a6cbb3fda56c055d3c17ccc8",
        #     "defaultSlippage": null,
        #     "feeCurrency": "USDT",
        #     "feeTokenAddress": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        #     "locked": false,
        #     "makerAltFee": null,
        #     "makerFee": "0.0025",
        #     "name": "EOS/USDT",
        #     "promotional": false,
        #     "quantityIncrement": "0.01",
        #     "quoteCurrency": "USDT",
        #     "quoteMinSize": "10",
        #     "quoteTokenAddress": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        #     "showOnLanding": false,
        #     "sortOrder": 46,
        #     "symbol": "EOSUSDT",
        #     "takerAltFee": null,
        #     "takerFee": "0.005",
        #     "tickSize": "0.0001"
        # }, ...]
        mapping = bidict()
        for market in markets:
            if utils.is_pair_information_valid(market):
                pair = combine_to_hb_trading_pair(base=market["baseCurrency"], quote=market["quoteCurrency"])
                mapping[market["symbol"]] = pair
                self._trading_pairs_fee_token[pair] = market["feeCurrency"]
                self._token_addresses[market["baseCurrency"]] = market["baseTokenAddress"]
                self._token_addresses[market["quoteCurrency"]] = market["quoteTokenAddress"]
                self._token_addresses[market["feeCurrency"]] = market["feeTokenAddress"]
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        params = {
            "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        }

        resp_json = await self._api_request(
            method=RESTMethod.GET,
            path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
            params=params
        )

        return float(resp_json["lastPrice"])
