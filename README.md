# aio_nameko_proxy

A standalone nameko rpc proxy for asyncio

### example
```python
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika.message import DeliveryMode
config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc"
}

async def run():
    async with AIOClusterRpcProxy(config, delivery_mode=DeliveryMode.NOT_PERSISTENT) as rpc:
        ret = await rpc.rpc_demo_service.normal_rpc("demo")

        ret_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
        await ret_obj.result()


if __name__ == '__main__':

    import asyncio
    loop = asyncio.get_event_loop()

    loop.run_until_complete(run())
```