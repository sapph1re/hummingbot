from decimal import Decimal
from typing import Any, Dict
from datetime import datetime

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "TIMEETH"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.0025"),
    taker_percent_fee_decimal=Decimal("0.0050"),
    buy_percent_fee_deducted_from_returns=True
)


def is_pair_information_valid(pair_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its market information
    :param pair_info: the market information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return not pair_info.get("locked", False)


def parse_timestamp(ts: str) -> float:
    """
    Converts TimeX timestamps like "2023-09-04T10:05:50.026856887" to normal timestamps
    """
    return datetime.strptime(ts[:26], "%Y-%m-%dT%H:%M:%S.%f").timestamp()


class TimeXConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="timex", const=True, client_data=None)
    timex_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: f"Enter your TimeX API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    timex_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: f"Enter your TimeX API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    timex_id_address: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: f"Enter your TimeX ID address",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )

    class Config:
        title = "timex"


KEYS = TimeXConfigMap.construct()
