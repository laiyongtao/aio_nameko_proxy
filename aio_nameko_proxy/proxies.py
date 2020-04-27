# coding=utf-8
import sys
import uuid
import json
import asyncio
from functools import partial
from aio_pika import (connect_robust,
                      Message,
                      ExchangeType,
                      DeliveryMode)

from .excs import ConfigError, deserialize
from .constants import *


class AIOClusterRpcProxy(object):

    def __init__(self, config, loop=None, *, time_out=None, con_time_out=None, **options):
        if not config:
            raise
        self.parse_config(config)
        self.virtual_service_name = "aio_rpc_proxy"
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.options = options
        self.connection = None
        self._time_out = time_out or DEFAULT_TIMEOUT
        self._con_time_out = con_time_out or DEFAULT_CON_TIMEOUT
        self._proxies = {}
        self.reply_listener = ReplyListener(self, time_out=self._con_time_out)
        self._proxies = {}

    def parse_config(self, config):
        if not isinstance(config, dict):
            raise ConfigError("config must be an instance of dict!")
        amqp_uri = config.get("AMQP_URI")
        if not amqp_uri:
            raise ConfigError('Can not find config key named the "AMQP_URI"')

        self._config = config

        self.amqp_uri = amqp_uri

        self._exchange_name = config.get(RPC_EXCHANGE_CONFIG_KEY, RPC_EXCHANGE_NAME)

    async def _connect(self):
        self.connection = await connect_robust(self.amqp_uri, loop=self.loop, timeout=self._con_time_out)
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


class Publisher(object):

    def __init__(self, exchange):
        self.exchange = exchange

    async def publish(self, msg, routing_key, *, mandatory=True,
                      immediate=False, timeout=None):
        await self.exchange.publish(
            msg, routing_key, mandatory=mandatory, immediate=immediate, timeout=timeout
        )


class ReplyListener(object):

    def __init__(self, cluster_proxy: AIOClusterRpcProxy, time_out=None):
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

    def get_reply_future(self, correlation_id):
        reply_future = asyncio.get_event_loop().create_future()
        self._reply_futures[correlation_id] = reply_future
        return reply_future

    async def handle_message(self, message):
        message.ack()

        correlation_id = message.properties.correlation_id
        future = self._reply_futures.pop(correlation_id, None)

        if future is not None:
            try:
                try:
                    body = json.loads(message.body)
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
    def __init__(self, service_name, cluster_proxy, time_out=None, con_time_out=None, **options):
        self.service_name = service_name
        self.cluster_proxy = cluster_proxy
        self.options = options
        self._time_out = time_out
        self._con_time_out = con_time_out
        self._proxies = {}

    def __getattr__(self, name):
        print(self._proxies)
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

    def __init__(self, reply_future, time_out=None):
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

    def __init__(self, service_name, method_name, cluster_proxy, time_out=None, con_time_out=None,
                 **options):
        self.service_name = service_name
        self.method_name = method_name
        self.options = self._set_default_options(options)
        self.reply_listener = cluster_proxy.reply_listener
        self.exchange = cluster_proxy.exchange
        self._time_out = time_out
        self._con_time_out = con_time_out
        self.publisher = Publisher(self.exchange)

    def _set_default_options(self, options):
        _options = options.copy()
        _options.setdefault("delivery_mode", DeliveryMode.PERSISTENT)
        # other options default set ...
        return _options

    async def _publish(self, msg):
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

    async def _call(self, *args, **kwargs):
        payload = {"args": args, "kwargs": kwargs}
        body = json.dumps(payload).encode("utf-8")
        reply_to = self.reply_listener.routing_key
        correlation_id = str(uuid.uuid4())

        msg = Message(
            body,
            content_type="application/json",
            reply_to=reply_to,
            correlation_id=correlation_id,
            **self.options
        )
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
            print(True)
            return DeliveryMode.PERSISTENT
        else:
            return DeliveryMode.NOT_PERSISTENT

    async def _sw_call(self, *args, **kwargs):
        '''switch from the default delivery_mode of the Message to another, and publish'''
        options = self.options.copy()
        delivery_mode = self._switch_delivery_mode(options["delivery_mode"])
        options.update(delivery_mode=delivery_mode)

        payload = {"args": args, "kwargs": kwargs}
        body = json.dumps(payload).encode("utf-8")
        reply_to = self.reply_listener.routing_key
        correlation_id = str(uuid.uuid4())

        msg = Message(
            body,
            content_type="application/json",
            reply_to=reply_to,
            correlation_id=correlation_id,
            **options
        )
        return await self._publish(msg)
