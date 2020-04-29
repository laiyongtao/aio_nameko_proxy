'''
reference the aio-pika.pool
'''
import asyncio
from aio_pika.pool import PoolInvalidStateError, ConstructorType
from typing import Union, AsyncContextManager
from .excs import ClientError


NumType = Union[int, float]


class ProxyPool(object):

    _inited = False
    def __init__(self, proxy_factory: ConstructorType,
                 pool_size: int = None, initial_size: int = None, time_out: NumType =None,
                 loop: asyncio.AbstractEventLoop = None):

        self.loop = loop or asyncio.get_event_loop()
        # if the origin proxy_factory need some args, you can use functools.partial or functools.partialmethod
        self._proxy_factory = proxy_factory
        self._created = 0
        self._closed = False
        self._created_proxies = set()
        self._free_proxies = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._pool_size = pool_size
        self._initial_size = initial_size or 0
        self._time_out = time_out

    async def init_proxies(self):
        self._inited = True
        for i in range(self._initial_size):
            proxy = await self._create_proxy()
            self.release_proxy(proxy)

    @property
    def _has_released(self):
        return self._free_proxies.qsize() > 0

    @property
    def _is_overflow(self) -> bool:
        if self._pool_size:
            return self._created >= self._pool_size or self._has_released
        return self._has_released

    async def _create_proxy(self):
        if self._closed:
            raise PoolInvalidStateError('create proxy operation on closed pool')

        async with self._lock:
            if self._is_overflow:
                if self._time_out is not None:
                    try:
                        proxy = await asyncio.wait_for(self._free_proxies.get(), timeout=self._time_out)
                    except asyncio.TimeoutError:
                        raise ClientError("Too many proxies in use")
                    return proxy
                return await self._free_proxies.get()

            proxy = await self._proxy_factory()
            self._created += 1
            self._created_proxies.add(proxy)
            return proxy

    async def get_proxy(self):
        if self._closed:
            raise PoolInvalidStateError('get operation on closed pool')
        if self._is_overflow:
            if self._time_out is not None:
                try:
                    proxy = await asyncio.wait_for(self._free_proxies.get(), timeout=self._time_out)
                except asyncio.TimeoutError:
                    raise ClientError("Too many proxies in use")
                return proxy
            return await self._free_proxies.get()
        return await self._create_proxy()

    def release_proxy(self, proxy):
        if self._closed:
            raise PoolInvalidStateError('put proxy operation on closed pool')
        self._free_proxies.put_nowait(proxy)


    async def close(self):
        async with self._lock:
            self._closed = True
            tasks = []

            for proxy in self._created_proxies:
                tasks.append(self.loop.create_task(proxy.close()))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._closed:
            return
        await asyncio.shield(self.close())

    def acquire(self) -> 'PoolItemContextManager':
        if self._closed:
            raise PoolInvalidStateError('acquire operation on closed pool')

        return PoolItemContextManager(self)


class PoolItemContextManager(AsyncContextManager):

    def __init__(self, pool):
        self.pool = pool
        self.item = None

    async def __aenter__(self):
        # noinspection PyProtectedMember
        self.item = await self.pool.get_proxy()
        return self.item

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.item is not None:
            self.pool.release_proxy(self.item)