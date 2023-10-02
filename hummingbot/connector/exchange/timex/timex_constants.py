from hummingbot.core.api_throttler.data_types import RateLimit

DEFAULT_DOMAIN = ""
HBOT_ORDER_ID_PREFIX = "HBOT-"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL = "https://plasma-relay-backend.timex.io/"
WSS_URL = "wss://plasma-relay-backend.timex.io/socket/relay"

PING_TIMEOUT = 60.0

MARKETS_PATH_URL = "public/markets"
ORDER_BOOK_PATH_URL = "public/orderbook/v2"
TICKERS_PATH_URL = "public/tickers"
ORDER_PATH_URL = "/trading/orders"
TRADES_PATH_URL = "/trading/trades"

PUBLIC_URL_POINTS_LIMIT_ID = "PublicPoints"
RATE_LIMITS = [
    RateLimit(limit_id=PUBLIC_URL_POINTS_LIMIT_ID, limit=900, time_interval=1),
]


# public static final Integer INTERNAL_ERROR = 0;
# public static final Integer UNSUPPORTED_OPERATION = 1;
# public static final Integer BAD_PARAMS = 4000;
# public static final Integer BAD_PARAMS_INSUFFICIENT_BALANCE = 4001;
# public static final Integer BAD_PARAMS_ORDERBOOK_EMPTY = 4002;
# public static final Integer BAD_PARAMS_2FA_CODE = 4003;
# public static final Integer BAD_PARAMS_2FA_CODE_REQUIRED = 4004;
# public static final Integer BAD_PARAMS_WITHDRAWAL_FEE_HAS_BEEN_CHANGED = 4005;
# public static final Integer BAD_PARAMS_WITHDRAWAL_VALUE_LOWER_THAN_FEE= 4006;
# public static final Integer BAD_PARAMS_WITHDRAWAL_VALUE_INCORRECT_SCALE = 4006;
# public static final Integer BAD_PARAMS_NOT_EMPTY_ORDERBOOK = 4007;
# public static final Integer BAD_PARAMS_NOT_FULL_MATCH = 4008;
# public static final Integer MATCHING_SLIPPAGE_ERROR = 4009;
# public static final Integer FORBIDDEN = 4300;
# public static final Integer UNAUTHORIZED = 4100;
# public static final Integer NOT_FOUND = 4400;
# public static final Integer SERVER_OVERLOAD = 4900;
# public static final Integer USER_OVERLOAD = 4901;
# public static final Integer CANNOT_MATCH_ORDERS_REQUIRE_AMOUNT_LT_ZERO = 5001;
# public static final Integer UNABLE_TO_ACQUIRE_DB_CONNECTION = 5002;
# public static final Integer WALLET_SERVICE_ERROR = 5003;
# public static final Integer CANNOT_CALC_QUOTE_FEE_RATE = 5004;
# public static final Integer CANCELLING_STATEMENT_DUE_STATEMENT_TIMEOUT = 5005;
# public static final Integer CANNOT_CREATE_EC_PAIR = 5050;
# public static final Integer UNEXPECTED_BEHAVIOR = 5051;
# public static final Integer PLASMA_ADDRESS_NOT_CONNECTED_TO_USER = 10002;
# public static final Integer LIMIT_NOT_SET = 10100;
# public static final Integer LIMIT_AMOUNT_EXCEED = 10101;
# public static final Integer LIMIT_TRADE_COUNT_EXCEED = 10102;
# public static final Integer ORDERBO0K_CALCULATION_INTERRUPTED_ERROR = 10201;
