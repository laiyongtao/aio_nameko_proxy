# coding=utf-8
import uuid
import json
import asyncio
from logging import getLogger
from .excs import ConfigError, deserialize
from aio_pika import (connect_robust,
                      Message,
                      ExchangeType)

_log = getLogger(__name__)


RPC_REPLY_QUEUE_TEMPLATE = 'rpc.reply-{}-{}'
RPC_REPLY_QUEUE_TTL = 300000  # ms (5 mins)
RPC_EXCHANGE_CONFIG_KEY = 'rpc_exchange'
RPC_EXCHANGE_NAME = 'nameko-rpc'


class AIOClusterRpcProxy(object):

    def __init__(self, config, loop=None, **options):
        if not config:
            raise
        self.parse_config(config)
        self.virtual_service_name = "aio_rpc_proxy"
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.options = options
        self.connection = None
        self._proxies = {}
        self.reply_listener = ReplyListener(self)

    def parse_config(self, config):
        if not isinstance(config, dict):
            raise ConfigError("config must be an instance of dict!")
        amqp_uri = config.get("AMQP_URI")
        if not amqp_uri:
            raise ConfigError('Can not find config key named the "AMQP_URI"')

        self._config = config

        self.amqp_uri = amqp_uri

        self._exchange_name = config.get(RPC_EXCHANGE_CONFIG_KEY, RPC_EXCHANGE_NAME)

    async def start(self):
        self.connection = await connect_robust(self.amqp_uri, loop=self.loop)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(self._exchange_name or RPC_EXCHANGE_NAME,
                                                            type=ExchangeType.TOPIC,
                                                            durable=True)
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

    def __init__(self, cluster_proxy: AIOClusterRpcProxy):
        self._reply_futures = {}
        self.cluster_proxy = cluster_proxy

    async def setup(self):

        reply_queue_uuid = uuid.uuid4()
        service_name = self.cluster_proxy.virtual_service_name

        queue_name = RPC_REPLY_QUEUE_TEMPLATE.format(
            service_name, reply_queue_uuid)

        self.routing_key = str(reply_queue_uuid)

        self.exchange = self.cluster_proxy.exchange

        self.queue = await self.cluster_proxy.channel.declare_queue(
            queue_name,
            arguments={
                'x-expires': RPC_REPLY_QUEUE_TTL
            }
        )

        await self.queue.bind(self.exchange, self.routing_key)
        await self.queue.consume(self.handle_message)

    async def stop(self):
        await self.queue.unbind(self.exchange, self.routing_key)

    def get_reply_future(self, correlation_id):
        reply_future = asyncio.get_event_loop().create_future()
        self._reply_futures[correlation_id] = reply_future
        return reply_future

    async def handle_message(self, message):
        message.ack()

        correlation_id = message.properties.correlation_id
        feature = self._reply_futures.pop(correlation_id, None)

        if feature is not None:
            try:
                body = json.loads(message.body)
            except Exception as e:
                feature.set_exception(e)
            else:
                feature.set_result(body)
        else:
            _log.debug("Unknown correlation id: %s", correlation_id)


class ServiceProxy(object):
    def __init__(self, service_name, cluster_proxy, **options):
        self.service_name = service_name
        self.cluster_proxy = cluster_proxy
        self.options = options

    def __getattr__(self, name):
        return MethodProxy(
            self.service_name,
            name,
            self.cluster_proxy,
            **self.options
        )


class RpcReply(object):
    resp_body = None

    def __init__(self, reply_future):
        self.reply_future = reply_future

    async def result(self):
        _log.debug('Waiting for RPC reply future %s', self)

        if self.resp_body is None:
            self.resp_body = await self.reply_future
            _log.debug('RPC reply future complete %s %s', self, self.resp_body)

        error = self.resp_body.get('error')
        if error:
            raise deserialize(error)
        return self.resp_body['result']


class MethodProxy(object):

    def __init__(self, service_name, method_name, cluster_proxy: AIOClusterRpcProxy, **options):
        self.service_name = service_name
        self.method_name = method_name
        self.options = options
        self.reply_listener = cluster_proxy.reply_listener
        self.exchange = cluster_proxy.exchange

        self.publisher = Publisher(self.exchange)

    async def _call(self, *args, **kwargs):
        routing_key = "{}.{}".format(self.service_name, self.method_name)

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

        future = self.reply_listener.get_reply_future(correlation_id)

        await self.publisher.publish(
            msg,
            routing_key
        )
        return RpcReply(future)

    async def call_async(self, *args, **kwargs):
        return await self._call(*args, **kwargs)

    async def __call__(self, *args, **kwargs):
        reply = await self._call(*args, **kwargs)
        return await reply.result()



