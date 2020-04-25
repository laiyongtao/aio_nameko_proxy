# coding=utf-8
import asyncio
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_pika.message import DeliveryMode
config = {
    "AMQP_URI": "pyamqp://guest:guest@127.0.0.1:5672",
    "rpc_exchange": "nameko-rpc"
}

async def run():

    '''
    If you want most of your messages to be non-persistent. Set the delivery mode parameter as
    DeliveryMode.NOT_PERSISTENT. Call sw_dlm_call when you need to send a persistent message.
    '''
    async with AIOClusterRpcProxy(config, delivery_mode=DeliveryMode.NOT_PERSISTENT) as rpc:
        # non-persistent msg call
        result = await rpc.rpc_demo_service.normal_rpc("demo")

        result_obj = await rpc.rpc_demo_service.normal_rpc.call_async("demo")
        result = await result_obj.result()

        # persistent msg call
        result = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call("demo")

        result_obj = await rpc.rpc_demo_service.normal_rpc.sw_dlm_call_async("demo")
        result = await result_obj.result()

    '''
    If you want most of your messages to be persistent. Set the delivery mode parameter as
    DeliveryMode.PERSISTENT. Call sw_dlm_call when you need to send a non-persistent message.
    '''
    async with AIOClusterRpcProxy(config, delivery_mode=DeliveryMode.PERSISTENT) as rpc:
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
