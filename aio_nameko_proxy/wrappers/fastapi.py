# coding=utf-8
from __future__ import absolute_import
import re
import asyncio
import aiotask_context as ctx
from typing import Any

from aio_nameko_proxy import AIOPooledClusterRpcProxy
from aio_nameko_proxy.constants import CAPITAL_CONFIG_KEYS

try:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.applications import ASGIApp
    from starlette.requests import Request
    from starlette.responses import Response
except ImportError:
    class BaseHTTPMiddleware(object):
        '''Fake starlette.middleware.base.BaseHTTPMiddleware'''

        def _miss(self, *args, **kwargs):
            raise RuntimeError("starlette is not installed")

        call_next = __call__ = dispatch = _miss
        del _miss

from . import rpc_cluster


class FastApiNamekoProxyMiddleware(AIOPooledClusterRpcProxy, BaseHTTPMiddleware):

    def __init__(self, app: "ASGIApp", config: "Any"):
        self.dispatch_func = self.dispatch
        self.app = app
        self.init_app(app, config)

    def init_app(self, app: "ASGIApp", config: "Any") -> None:

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

        while hasattr(app, "app"):
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

        rpc_cluster._set(self)

    async def get_proxy(self):
        proxy = ctx.get('_nameko_rpc_proxy', None)
        if not proxy:
            proxy = await super(FastApiNamekoProxyMiddleware, self).get_proxy()
            ctx.set('_nameko_rpc_proxy', proxy)
        return proxy

    def remove(self) -> None:
        proxy = ctx.get('_nameko_rpc_proxy', None)
        if proxy is not None:
            self.release_proxy(proxy)

    async def dispatch(self, request: "Request", call_next: "RequestResponseEndpoint") -> "Response":
        try:
            response = await call_next(request)
        finally:
            self.remove()
        return response
