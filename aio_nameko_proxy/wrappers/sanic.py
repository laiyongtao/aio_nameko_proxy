# coding=utf-8
from __future__ import absolute_import
import re
import aiotask_context as ctx
from aio_nameko_proxy import AIOPooledClusterRpcProxy


class SanicNamekoClusterRpcProxy(AIOPooledClusterRpcProxy):

    def __init__(self, app=None):
        if app:
            self.init_app(app)

    def init_app(self, app):
        config = dict()
        for k, v in app.config.items():
            match = re.match(r"NAMEKO_(?P<name>.*)", k)
            if match:
                name = match.group("name")
                if name == "AMQP_URI":
                    config[name] = v
                    continue
                name = name.lower()
                config[name] = v
        self.parse_config(config)

        @app.listener('after_server_start')
        async def _set_aiotask_factory(app, loop):
            loop.set_task_factory(ctx.task_factory)

        @app.listener('after_server_start')
        async def _init_proxy_pool(app, loop):
            self.loop = loop
            await self.init_pool()

        @app.listener('before_server_stop')
        async def _close_proxy_pool(app, loop):
            await self.close()

        @app.middleware('response')
        async def release_nameko_proxy(request, response):
            proxy = ctx.get('_nameko_rpc_proxy', None)
            if proxy is not None:
                self.release_proxy(proxy)

    async def get_proxy(self):
        proxy = ctx.get('_nameko_rpc_proxy', None)
        if not proxy:
            proxy = await super(SanicNamekoClusterRpcProxy, self).get_proxy()
            ctx.set('_nameko_rpc_proxy', proxy)
        return proxy

