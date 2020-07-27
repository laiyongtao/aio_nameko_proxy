# coding=utf-8
import sys
import uuid
import asyncio
import ssl
from enum import Enum
from typing import Optional, Any

import aiormq
from yarl import URL
from aio_pika import (connect_robust,
                      Message,
                      IncomingMessage,
                      ExchangeType,
                      DeliveryMode,
                      Exchange)
from aio_pika.types import TimeoutType
from nameko.serialization import setup as serialization_setup
from kombu.serialization import loads, dumps, prepare_accept_content

from .excs import ConfigError, deserialize
from .constants import *
from .pool import ProxyPool


class AIOClusterRpcProxy(object):

    def __init__(self, config: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        if not config:
            raise ConfigError("Please provide config dict")
        self.parse_config(config)
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.virtual_service_name = "aio_rpc_proxy"
        self.connection = None
        self._proxies = {}

        self.reply_listener = ReplyListener(self, time_out=self._con_time_out)

    def parse_config(self, config: dict):
        if not isinstance(config, dict):
            raise ConfigError("config must be an instance of dict!")

        self._config = config
        _config = config.copy()

        amqp_uri = _config.pop("AMQP_URI", None)
        if not amqp_uri:
            raise ConfigError('Can not find config key named the "AMQP_URI"')

        self.url = URL(amqp_uri)

        self.serializer, self.accept = serialization_setup(_config)

        self._exchange_name = _config.pop(RPC_EXCHANGE_CONFIG_KEY, RPC_EXCHANGE_NAME)

        self._time_out = _config.pop('time_out', DEFAULT_TIMEOUT)
        self._con_time_out = _config.pop('con_time_out', DEFAULT_CON_TIMEOUT)
        self.ssl_options = _config.pop(AMQP_SSL_CONFIG_KEY, {})
        self.options = _config

    async def _connect(self):
        ssl_ = False
        if self.ssl_options:
            ssl_ = True
            # For compatibility with aiprmq
            if "ca_certs" in self.ssl_options:
                self.ssl_options.setdefault("cafile", self.ssl_options["ca_certs"])
            if "cert_reqs" in self.ssl_options:
                self.ssl_options.setdefault("no_verify_ssl",
                                            ssl.CERT_REQUIRED if self.ssl_options["cert_reqs"] == ssl.CERT_NONE
                                            else ssl.CERT_NONE)
            # For compatibility with yarl
            for k, v in self.ssl_options.items():
                if isinstance(v, Enum): self.ssl_options[k] = v.value

        self.connection = await connect_robust(
            host=self.url.host,
            port=self.url.port,
            login=self.url.user,
            password=self.url.password,
            ssl=ssl_,
            ssl_options=self.ssl_options,
            loop=self.loop,
            timeout=self._con_time_out,
            **self.url.query,
        )
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(self._exchange_name or RPC_EXCHANGE_NAME,
                                                            type=ExchangeType.TOPIC,
                                                            durable=True,
                                                            timeout=self._con_time_out)

    async def start(self):
        await self._connect()
        await self.reply_listener.setup()
        return self

    async def close(self):
        await self.reply_listener.stop()
        await self.connection.close()

    async def __aenter__(self):
        if not self.connection:
            await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __getattr__(self, name):
        if name not in self._proxies:
            self._proxies[name] = ServiceProxy(name, self, **self.options)
        return self._proxies[name]


class AIOPooledClusterRpcProxy(object):
    _pool = None
    _closed = False

    def __init__(self, config: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        if not config:
            raise ConfigError("Please provide config dict")
        self.parse_config(config)
        self.loop = loop

    def parse_config(self, config: dict):
        self.pool_size = config.pop("pool_size", 5)
        self.initial_size = config.pop("initial_size", 2)
        self.con_time_out = config.get('con_time_out', None)

        self._config = config.copy()

    async def init_pool(self):
        if self._pool is None:
            self._pool = ProxyPool(self._make_rpc_proxy,
                                   pool_size=self.pool_size,
                                   initial_size=self.initial_size,
                                   loop=self.loop,
                                   time_out=self.con_time_out)
        await self._pool.init_proxies()

    async def _make_rpc_proxy(self):
        cluster_rpc = AIOClusterRpcProxy(config=self._config)
        return await cluster_rpc.start()

    async def get_proxy(self):
        if not self._pool:
            raise ConfigError("Please inie your cluster")
        return await self._pool.get_proxy()

    def release_proxy(self, proxy: AIOClusterRpcProxy):
        if isinstance(proxy, AIOClusterRpcProxy):
            self._pool.release_proxy(proxy)

    async def close(self):
        self._closed = True
        await asyncio.shield(self._pool.close())

    async def __aenter__(self):
        await self.init_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._closed:
            return
        await self.close()

    def acquire(self):
        return self._pool.acquire()


class Publisher(object):

    def __init__(self, exchange: Exchange):
        self.exchange = exchange

    async def publish(self, msg: Message, routing_key: str, *, mandatory: bool = True,
                      immediate: bool = False, timeout: Optional[TimeoutType] = None):
        await self.exchange.publish(
            msg, routing_key, mandatory=mandatory, immediate=immediate, timeout=timeout
        )


class ReplyListener(object):

    def __init__(self, cluster_proxy: AIOClusterRpcProxy, time_out: Optional[TimeoutType] = None):
        self._reply_futures = {}
        self.cluster_proxy = cluster_proxy
        self._time_out = time_out

    async def setup(self):

        reply_queue_uuid = uuid.uuid4()
        service_name = self.cluster_proxy.virtual_service_name

        queue_name = RPC_REPLY_QUEUE_TEMPLATE.format(
            service_name, reply_queue_uuid)

        self.routing_key = str(reply_queue_uuid)

        self.exchange = self.cluster_proxy.exchange

        self.queue = await self.cluster_proxy.channel.declare_queue(queue_name,
                                                                    arguments={
                                                                        'x-expires': RPC_REPLY_QUEUE_TTL
                                                                    },
                                                                    timeout=self._time_out)

        await self.queue.bind(self.exchange, self.routing_key, timeout=self._time_out)
        await self.queue.consume(self.handle_message, timeout=self._time_out)

    async def stop(self):
        await self.queue.unbind(self.exchange, self.routing_key, timeout=self._time_out)

    def get_reply_future(self, correlation_id: str):
        reply_future = asyncio.get_event_loop().create_future()
        self._reply_futures[correlation_id] = reply_future
        return reply_future

    async def handle_message(self, message: IncomingMessage):
        message.ack()

        correlation_id = message.correlation_id
        future = self._reply_futures.pop(correlation_id, None)

        if future is not None:
            try:
                try:
                    accept = self.accept = prepare_accept_content(self.cluster_proxy.accept)
                    body = loads(message.body,
                                 content_type=message.content_type,
                                 content_encoding=message.content_encoding,
                                 accept=accept)
                except Exception as e:
                    future.set_exception(e)
                else:
                    future.set_result(body)
            except asyncio.InvalidStateError as e:
                # for catching the errors after the future obj was cancelled by the asyncio.wait_for timeout.
                sys.stdout.write("{}, correlation id: {}".format(e, correlation_id))
        else:
            sys.stdout.write("Unknown correlation id: {}".format(correlation_id))


class ServiceProxy(object):
    def __init__(self, service_name: str, cluster_proxy: AIOClusterRpcProxy, time_out: Optional[TimeoutType] = None,
                 con_time_out: Optional[TimeoutType] = None, **options):
        self.service_name = service_name
        self.cluster_proxy = cluster_proxy
        self.options = options
        self._time_out = time_out
        self._con_time_out = con_time_out
        self._proxies = {}

    def __getattr__(self, name):
        if name not in self._proxies:
            self._proxies[name] = MethodProxy(self.service_name,
                                              name,
                                              self.cluster_proxy,
                                              time_out=self._time_out,
                                              con_time_out=self._con_time_out,
                                              **self.options)
        return self._proxies[name]


class RpcReply(object):
    resp_body = None

    def __init__(self, reply_future: asyncio.Future, time_out: Optional[TimeoutType] = None):
        self.reply_future = reply_future
        self._time_out = time_out

    async def result(self):

        if self.resp_body is None:
            self.resp_body = await asyncio.wait_for(self.reply_future,
                                                    timeout=self._time_out)
        error = self.resp_body.get('error')
        if error:
            raise deserialize(error)
        return self.resp_body['result']


class MethodProxy(object):

    def __init__(self, service_name: str, method_name: str, cluster_proxy: AIOClusterRpcProxy,
                 time_out: Optional[TimeoutType] = None, con_time_out: Optional[TimeoutType] = None,
                 **options):
        self.cluster_proxy = cluster_proxy
        self.service_name = service_name
        self.method_name = method_name
        self.options = self._set_default_options(options)
        self.reply_listener = cluster_proxy.reply_listener
        self.exchange = cluster_proxy.exchange
        self._time_out = time_out
        self._con_time_out = con_time_out
        self.publisher = Publisher(self.exchange)

    def _set_default_options(self, options: dict):
        _options = dict()
        for k, v in options.items():
            if (
                    k not in aiormq.spec.Basic.Properties.__slots__ or
                    k == "reply_to" or k == "correlation_id" or
                    k == "content_encoding" or k == "content_type"
            ):
                continue
            _options.update({k: v})
        _options.setdefault("delivery_mode", DeliveryMode.PERSISTENT)
        # other options default set ...
        return _options

    async def _publish(self, msg: Message):
        correlation_id = msg.correlation_id
        routing_key = "{}.{}".format(self.service_name, self.method_name)
        future = self.reply_listener.get_reply_future(correlation_id)

        await self.publisher.publish(
            msg,
            routing_key,
            timeout=self._con_time_out
        )
        return RpcReply(future)

    async def call_async(self, *args, **kwargs):
        return await self._call(*args, **kwargs)

    async def __call__(self, *args, **kwargs):
        reply = await self._call(*args, **kwargs)
        return await reply.result()

    def make_msg(self, payload: Any, options: dict):

        reply_to = self.reply_listener.routing_key
        correlation_id = str(uuid.uuid4())

        serializer = self.cluster_proxy.serializer
        content_type, content_encoding, body = dumps(payload, serializer)
        if isinstance(body, str): body = bytes(body, content_encoding)

        msg = Message(
            body,
            content_type=content_type,
            content_encoding=content_encoding,
            reply_to=reply_to,
            correlation_id=correlation_id,
            **options
        )
        return msg

    async def _call(self, *args, **kwargs):

        payload = {"args": args, "kwargs": kwargs}
        msg = self.make_msg(payload, options=self.options)

        return await self._publish(msg)

    async def sw_dlm_call(self, *args, **kwargs):
        '''switch from the default delivery_mode of the Message to another, and call the remote method'''
        reply = await self._sw_call(*args, **kwargs)
        return await reply.result()

    async def sw_dlm_call_async(self, *args, **kwargs):
        '''switch from the default delivery_mode of the Message to another, and call the remote method async'''
        return await self._sw_call(*args, **kwargs)

    def _switch_delivery_mode(self, delivery_mode):
        '''switch from the default delivery_mode to another'''
        if delivery_mode == DeliveryMode.NOT_PERSISTENT:
            return DeliveryMode.PERSISTENT
        else:
            return DeliveryMode.NOT_PERSISTENT

    async def _sw_call(self, *args, **kwargs):
        '''switch from the default delivery_mode of the Message to another, and publish'''
        options = self.options.copy()
        delivery_mode = self._switch_delivery_mode(options["delivery_mode"])
        options.update(delivery_mode=delivery_mode)

        payload = {"args": args, "kwargs": kwargs}
        msg = self.make_msg(payload, options=options)

        return await self._publish(msg)
