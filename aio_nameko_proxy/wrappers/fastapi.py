# coding=utf-8
from __future__ import absolute_import
import re
import asyncio
import aiotask_context as ctx
from typing import cast, Any

from aio_nameko_proxy import AIOPooledClusterRpcProxy
from aio_nameko_proxy.constants import CAPITAL_CONFIG_KEYS

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

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.routing import Router
    from starlette.applications import ASGIApp
except ImportError:
    class BaseHTTPMiddleware(object):
        '''Fake starlette.middleware.base.BaseHTTPMiddleware'''

        def _miss(self, *args, **kwargs):
            raise RuntimeError("starlette is not installed")

        call_next = __call__ = dispatch = _miss
        del _miss

    class Router(object):
        '''Fake starlette.routing.Router'''

        def _miss(self, *args, **kwargs):
            raise RuntimeError("starlette is not installed")

        on_event = _miss
        del _miss


_cluster = ContextVar("fastapi_nameko_cluster")


class FastApiNamekoProxyMiddleware(AIOPooledClusterRpcProxy, BaseHTTPMiddleware):

    def __init__(self,
            app,  # type: ASGIApp
            config  # type: Any
        ):
        self.dispatch_func = self.dispatch
        self.app = app
        self.init_app(app, config)

    def init_app(self,
            app,  # type: ASGIApp
            config  # type: Any
        ):

        _config = dict()
        for k in dir(config):
            match = re.match(r"NAMEKO_(?P<name>.*)", k)
            if match:
                name = match.group("name")
                if name in CAPITAL_CONFIG_KEYS:
                    _config[name] = getattr(config, k)
                    continue
                _config[name.lower()] = getattr(config, k)
        self.parse_config(_config)

        while not isinstance(app, Router):
            print("app", app)
            app = app.app

        @app.on_event("startup")
        async def _set_aiotask_factory():
            loop = asyncio._get_running_loop()
            loop.set_task_factory(ctx.task_factory)
            self.loop = loop

        @app.on_event("startup")
        async def _init_proxy_pool():
            await self.init_pool()

        @app.on_event("shutdown")
        async def _close_proxy_pool():
            await self.close()

        _cluster.set(self)

    async def get_proxy(self):
        proxy = ctx.get('_nameko_rpc_proxy', None)
        if not proxy:
            proxy = await super(FastApiNamekoProxyMiddleware, self).get_proxy()
            ctx.set('_nameko_rpc_proxy', proxy)
        return proxy

    def remove(self):
        proxy = ctx.get('_nameko_rpc_proxy', None)
        if proxy is not None:
            self.release_proxy(proxy)

    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
        finally:
            self.remove()
        return response


class Cluster(object):
    def __getattr__(self, item):
        instance = _cluster.get(None)
        if not instance:
            raise RuntimeError("Please initialize your cluster before using")
        return getattr(instance, item)


fastapi_rpc = cast(FastApiNamekoProxyMiddleware, Cluster())
