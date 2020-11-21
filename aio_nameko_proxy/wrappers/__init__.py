# coding=utf-8
import logging
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_nameko_proxy.pool import PoolItemContextManager


class _Cluster(object):

    def __init__(self):
        self.instance = None

    def _set(self, obj):
        if self.instance is None:
            self.instance = obj
            return
        if type(self.instance) == type(obj):
            return

        self.instance = obj
        logging.warning("Reset the cluster instance from {} to {}!".format(type(self.instance), type(obj)))

    def __getattr__(self, name):
        if not self.instance:
            raise RuntimeError("Please initialize your cluster before using")
        return getattr(self.instance, name)


class _ForHint:
    async def get_proxy(self):
        pass

    def remove(self) -> None:
        pass

    def release_proxy(self, proxy: "AIOClusterRpcProxy") -> None:
        pass

    def acquire(self) -> PoolItemContextManager:
        pass


from typing import cast

rpc_cluster = cast(_ForHint, _Cluster())

from .sanic import SanicNamekoClusterRpcProxy
from .fastapi import FastApiNamekoProxyMiddleware
