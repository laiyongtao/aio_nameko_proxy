# coding=utf-8
from nameko.exceptions import RemoteError, deserialize, deserialize_to_instance

class ConfigError(Exception):
    pass

class ClientError(Exception):
    pass
