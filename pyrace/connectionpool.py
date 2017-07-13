"""Provides custom `ConnectionPool`\s that use our custom `Connection`\s."""

from .connection import HTTPConnection, HTTPSConnection

import requests.packages.urllib3 as urllib3


# The default HTTPConnectionPool has a class-level ConnectionCls variable
# that contains the class used to create Connection objects.
# We override this value at the instance level to use our Connection instead.
class HTTPConnectionPool(urllib3.connectionpool.HTTPConnectionPool):
    ConnectionCls = HTTPConnection

class HTTPSConnectionPool(urllib3.connectionpool.HTTPSConnectionPool):
    ConnectionCls = HTTPSConnection