#  _ _ _      _     _    _   _ _      _ _ _      _ _ _      _ _
# |_|_|_|_   |_|   |_|  |_|_|_|_|   _|_|_|_|   _|_|_|_|   _|_|_|
# |_|   |_|  |_|   |_|  |_|_|      |_|   |_|  |_|        |_|_|_|_|
# |_|_ _|_|  |_|_ _|_|  |_|        |_|_ _|_|  |_|_ _ _   |_|_ _ _
# |_|_|_|      |_|_|_|  |_|          |_|_|_|    |_|_|_|    |_|_|_|
# |_|           _ _|_|
# |_|          |_|_|
#

"""
pyrace is an HTTP[S] race condition auditing package built using the `Requests`_ library.

.. _requests: http://docs.python-requests.org/en/master/


Examples
----------
Single :class:`~requests.Request` per worker::

    >>> driver = pyrace.Driver()
    >>> request = requests.Request('GET', 'http://now.httpbin.org')
    >>> threads = driver.process(request, thread_count = 2)
    >>> [t.response.json()['now']['epoch'] for t in threads]
    [1497300394.5125718, 1497300394.5126784]

Multiple :class:`~requests.Request`\s per worker::

    >>> driver = pyrace.Driver()
    >>> req1 = requests.Request('GET', 'http://httpbin.org/get?foo=bar')
    >>> req2 = requests.Request('POST', 'http://httpbin.org/post?baz=qux')
    >>> work_queue = [req1, req2]
    >>> threads = driver.process(work_queue, thread_count = 2)
    >>> [t.all_responses for t in threads]
    [[<Response [200]>, <Response [200]>], [<Response [200]>, <Response [200]>]]

Evaluation of embedded statements in :class:`~requests.Request`\s::

    >>> driver = pyrace.Driver()
    >>> data = {'thread': '<<<self.thread_num>>>', 'rand': '<<<random.random()>>>'}
    >>> request = requests.Request('POST', 'http://httpbin.org/post', data = data)
    >>> threads = driver.process(request, thread_count = 2, do_eval = True)
    >>> [t.response.json()['form'] for t in threads]
    [{u'rand': u'0.405020220768', u'thread': u'0'}, {u'rand': u'0.466687005524', u'thread': u'1'}]

For more detailed demonstrations see the :file:`examples/` source code directory.
"""

from .__version__ import __title__, __description__, __url__, __version__
from .__version__ import __author__, __author_email__, __copyright__, __license__

import logging
import requests

from .driver import Driver
from .thread import Thread, InvalidWorkItem
from .adapter import HTTPAdapter
from .connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from .connection import BaseConnection, HTTPConnection, HTTPSConnection
