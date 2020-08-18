# coding=utf-8
from aio_nameko_proxy import AIOClusterRpcProxy
from aio_nameko_proxy.pool import PoolItemContextManager
try:
    from contextvars import ContextVar
except ImportError:
    class ContextVar(object):
        '''Fake contextvars.ContextVar'''

        def __init__(self, *args, **kwargs):
            pass

        def _miss(self, *args, **kwargs):
            raise RuntimeError("contextvars is not installed")

        @property
        def name(self):
            return self._miss()

        get = set = reset = _miss
        del _miss


class _Cluster(object):
    def __init__(self, ctx: "ContextVar"):
        self.ctx = ctx
        self.token = None

    def _set(self, obj):
        if self.token is not None:
            self.ctx.reset(self.token)
        self.token = self.ctx.set(obj)

    def __getattr__(self, name):
        instance = self.ctx.get(None)
        if not instance:
            raise RuntimeError("Please initialize your cluster before using")
        return getattr(instance, name)

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

__rpc_cluster = ContextVar("nameko_cluster")
rpc_cluster = cast(_ForHint, _Cluster(__rpc_cluster))

from .sanic import SanicNamekoClusterRpcProxy
from .fastapi import FastApiNamekoProxyMiddleware