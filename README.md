# aio-nameko-proxy

A standalone nameko rpc proxy for asyncio and a wrapper for using nameko rpc proxy with Sanic. 

This project is based on aio-pika and reference the source code of official nameko project and aio-pika.

### examples:
#### standalone AIOClusterRpcProxy
If you want most of your messages to be persistent(default). Set the delivery mode parameter as
DeliveryMode.PERSISTENT, Call sw_dlm_call when you need to send a non-persistent message.
```python
import ssl
import asyncio
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika import DeliveryMode

config = {
    "AMQP_URI": "amqp://guest:guest@127.0.0.1:5672",  # Required, 
    "rpc_exchange": "nameko-rpc",
    "time_out": 30, 
    "con_time_out": 5, 
    "delivery_mode": DeliveryMode.PERSISTENT,
    "serializer": "my_serializer",
    "ACCEPT": ["pickle", "json", "my_serializer"],
    "SERIALIZERS": {
        "my_serializer": {
            "encoder": "my_slizer.dumps",
            "decoder": "my_slizer.loads",
            "content_type": "my-content-type",
            "content_encoding": "utf-8"
        }
    },
    # If SSL is configured, Remember to change the URI to TLS port. eg: "amqps://guest:guest@127.0.0.1:5671"
    "AMQP_SSL": {
        'ca_certs': 'certs/ca_certificate.pem',  # or 'cafile': 'certs/ca_certificate.pem',
        'certfile': 'certs/client_certificate.pem',
        'keyfile': 'certs/client_key.pem',
        'cert_reqs': ssl.CERT_REQUIRED
    }
}

async def run():

    async with AIOClusterRpcProxy(config) as rpc:
            # time_out: the time_out of waitting the remote method result.
            # con_time_out: the time_out of connecting to the rabbitmq server or binding the queue, consume and so on.

            # persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc("demo")
    
            reply_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
            result = await reply_obj.result()
    
            # non-persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")
    
            reply_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
            result = await reply_obj.result()


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

If you want most of your messages to be non-persistent(persistent is default). Set the delivery mode parameter as
DeliveryMode.NOT_PERSISTENT, Call sw_dlm_call when you need to send a persistent message.
```python
import asyncio
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika import DeliveryMode
config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc",
    "time_out": 30, 
    "con_time_out": 5, 
    "delivery_mode": DeliveryMode.NOT_PERSISTENT
}

async def run():
    async with AIOClusterRpcProxy(config) as rpc:
            # non-persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc("demo")
    
            reply_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
            result = await reply_obj.result()
    
            # persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")
    
            reply_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
            result = await reply_obj.result()


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```
#### AIOPooledClusterRpcProxy
```python
import asyncio
from aio_nameko_proxy import AIOPooledClusterRpcProxy
from aio_pika import DeliveryMode

config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc",
    "time_out": 30, 
    "con_time_out": 5,
    "pool_size": 10,
    "initial_size": 2,
    "delivery_mode": DeliveryMode.NOT_PERSISTENT
}


async def run():

    async with AIOPooledClusterRpcProxy(config) as proxy_pool:
    
            async with proxy_pool.acquire() as rpc:
                result = await rpc.rpc_demo_service.normal_rpc("demo")


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

#### Sanic Wrapper
```python
import ssl
from sanic import Sanic
from sanic.response import json
from aio_pika import DeliveryMode
from aio_nameko_proxy.wrappers import SanicNamekoClusterRpcProxy

class Config(object):
    # AMQP_URI: Required
    NAMEKO_AMQP_URI = "pyamqp://guest:guest@127.0.0.1:5672"
    # rpc_exchange
    NAMEKO_RPC_EXCHANGE = "nameko-rpc"
    # pool_size
    NAMEKO_POOL_SIZE = 60
    # initial_size
    NAMEKO_INITIAL_SIZE = 60
    # time_out
    NAMEKO_TIME_OUT = 30
    # con_time_out
    NAMEKO_CON_TIME_OUT = 5
    # serializer
    NAMEKO_SERIALIZER = "json"
    # ACCEPT
    NAMEKO_ACCEPT = ["pickle", "json"]
    # SERIALIZERS: custom serializers
    NAMEKO_SERIALIZERS = {
        "my_serializer": {
            "encoder": "my_slizer.dumps",
            "decoder": "my_slizer.loads",
            "content_type": "my-content-type",
            "content_encoding": "utf-8"
        }
    }
    # AMQP_SSL: ssl configs
    NAMEKO_AMQP_SSL = {
        'ca_certs': 'certs/ca_certificate.pem',  # or 'cafile': 'certs/ca_certificate.pem',
        'certfile': 'certs/client_certificate.pem',
        'keyfile': 'certs/client_key.pem',
        'cert_reqs': ssl.CERT_REQUIRED
    }
    # delivery_mode
    NAMEKO_DELIVERY_MODE = DeliveryMode.PERSISTENT
    # other supported properties of aio-pika.Message, the key name format is "NAMEKO_{}".format(property_name.upper())
    # ...


app = Sanic("App Name")
app.config.from_object(Config)

# rpc_cluster = SanicNamekoClusterRpcProxy(app)
# or
rpc_cluster = SanicNamekoClusterRpcProxy()
rpc_cluster.init_app(app)


@app.route("/")
async def test(request):
    
    rpc = await rpc_cluster.get_proxy()

    result = await rpc.rpc_demo_service.normal_rpc("demo")

    reply_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
    result = await reply_obj.result()

    result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")

    reply_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
    result = await reply_obj.result()

    return json({"hello": "world"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```