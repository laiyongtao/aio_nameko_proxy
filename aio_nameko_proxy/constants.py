# coding=utf-8
from nameko.constants import (AMQP_URI_CONFIG_KEY,
                              RPC_EXCHANGE_CONFIG_KEY,
                              SERIALIZERS_CONFIG_KEY,
                              ACCEPT_CONFIG_KEY,
                              AMQP_SSL_CONFIG_KEY)
from nameko.rpc import (RPC_REPLY_QUEUE_TEMPLATE,
                        RPC_REPLY_QUEUE_TTL)


RPC_EXCHANGE_NAME = 'nameko-rpc'

DEFAULT_TIMEOUT = 30
DEFAULT_CON_TIMEOUT = 3

CAPITAL_CONFIG_KEYS = (AMQP_URI_CONFIG_KEY,
                       SERIALIZERS_CONFIG_KEY,
                       ACCEPT_CONFIG_KEY,
                       AMQP_SSL_CONFIG_KEY)