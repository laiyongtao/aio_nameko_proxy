# aio_nameko_proxy

A standalone nameko rpc proxy for asyncio. This project is based on aio-pika and reference the source code of official nameko project.

### example:
If you want most of your messages to be persistent(default). Set the delivery mode parameter as
DeliveryMode.PERSISTENT. Call sw_dlm_call when you need to send a non-persistent message.
```python
import asyncio
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika.message import DeliveryMode
config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc"
}

async def run():
    async with AIOClusterRpcProxy(config, time_out=30, con_time_out=5, delivery_mode=DeliveryMode.PERSISTENT) as rpc:
            # time_out: the time_out of waitting the remote method result.
            # con_time_out: the time_out of connecting to the rabbitmq server or binding the queue, consume and so on.

            # persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc("demo")
    
            result_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
            result = await result_obj.result()
    
            # non-persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")
    
            result_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
            result = await result_obj.result()


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

If you want most of your messages to be non-persistent(persistent is default). Set the delivery mode parameter as
DeliveryMode.NOT_PERSISTENT. Call sw_dlm_call when you need to send a persistent message.
```python
import asyncio
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika.message import DeliveryMode
config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc"
}

async def run():
    async with AIOClusterRpcProxy(config, time_out=30, con_time_out=5, delivery_mode=DeliveryMode.NOT_PERSISTENT) as rpc:
            # non-persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc("demo")
    
            result_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
            result = await result_obj.result()
    
            # persistent msg call
            result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")
    
            result_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
            result = await result_obj.result()


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```