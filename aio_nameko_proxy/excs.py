# coding=utf-8

class ConfigError(Exception):
    pass


class RemoteError(Exception):
    """ Exception to raise at the caller if an exception occurred in the
    remote worker.
    """

    def __init__(self, exc_type=None, value=""):
        self.exc_type = exc_type
        self.value = value
        message = '{} {}'.format(exc_type, value)
        super(RemoteError, self).__init__(message)


def deserialize(data):
    """ Deserialize `data` to an exception instance.

    If the `exc_path` value matches an exception registered as
    ``deserializable``, return an instance of that exception type.
    Otherwise, return a `RemoteError` instance describing the exception
    that occurred.
    """

    exc_type = data.get('exc_type')
    value = data.get('value')
    return RemoteError(exc_type=exc_type, value=value)
