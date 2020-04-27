import asyncio
from aio_pika.pool import Pool, PoolInvalidStateError, ConstructorType, T

from .excs import ClientError

class ConnectionPool(Pool):

    def __init__(self, constructor: ConstructorType, *args,
                 max_size: int = None, loop: asyncio.AbstractEventLoop = None, time_out=None):
        super(ConnectionPool, self).__init__(constructor, *args, max_size=max_size, loop=loop)
        self._time_out = time_out

    async def _create_item(self) -> T:
        if self.__closed:
            raise PoolInvalidStateError('create item operation on closed pool')

        async with self.__lock:
            if self._is_overflow:
                if self._time_out is not None:
                    try:
                        _item = await asyncio.wait_for(self.__items.get(), timeout=self._time_out)
                    except asyncio.TimeoutError:
                        raise ClientError("Too many connections in use")
                    return _item
                else:
                    return await self.__items.get()

            item = await self.__constructor(*self.__constructor_args)
            self.__created += 1
            self.__item_set.add(item)
            return item

    async def _get(self) -> T:
        if self.__closed:
            raise PoolInvalidStateError('get operation on closed pool')

        if self._is_overflow:
            if self._time_out is not None:
                try:
                    _item = await asyncio.wait_for(self.__items.get(), timeout=self._time_out)
                except asyncio.TimeoutError:
                    raise ClientError("Too many connections in use")
                return _item
            else:
                return await self.__items.get()
        return await self._create_item()