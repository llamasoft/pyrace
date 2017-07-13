"""Provides custom `Connection`\s for use with :class:`HTTPAdapter`\s."""

import logging
import socket
import threading
import time
import random

from select import select

import requests.packages.urllib3 as urllib3


_LOG = logging.getLogger(__name__)


_gai_lock   = threading.RLock()
_gai_cache  = {}
_gai_expiry = 10
"""
Python or the OS may (or may not) do some caching of :func:`socket.getaddrinfo` results.
On my setup, calls to :func:`~socket.getaddrinfo` from the same thread yield the same result,
but calls across threads occasionally return variations.  By caching :func:`~socket.getaddrinfo`
results, we ensure each `Connection` uses the same IP address values and ordering.
"""


"""
Creates a connection class that inherits from the specified :mod:`urllib3` `Connection` class.

Notes
-------
The primary difference between this `Connection` class and the default `Connection` classes is that
we intentionally stall on sending the final two bytes of any request until a custom Event fires.
This ensures that the sending of all parallel requests completes at *almost* exactly the same time.

The decision to withhold the last *two* bytes instead of the last *single* byte was deliberate.
HTTP methods that include a request body will always include a ``Content-Length`` header.
For those HTTP requests, withholding just the final byte will suffice; the server can't proceed
without the whole request body. For methods without a request body, the HTTP request ends with
an empty line (i.e. ``\r\n\r\n``). Delaying only the final byte allows the server to receive
``\r\n\r`` which is just enough information to determine that the next line will be blank.
I don't know if any server would act on a request that quickly, but to be safe, delaying
the last *two* bytes means the final ``\r\n`` is delayed, fully preventing "early" processing.
"""
class BaseConnection(object):
    """
    A :class:`~urllib3.HTTPConnection` wrapper that synchronizes the final bytes of a request.


    Parameters
    ------------
    race_args : dict
        Arguments for this class and its parent :class:`~.Thread`.
        Entries relevant to this class are:

        thread_num : int
            The thread number associated with our parent :class:`~.Thread`.
        shared : dict
            A shared dict between this `Connection` and its parent classes.
        sync_event : threading.Event
            Per-thread state synchronization :class:`~threading.Event`.
            We set `sync_event` just before waiting on `send_event` and/or `read_event`.
            This indicates to the parent `Driver` that our class is ready to proceed.
            Once all `Thread`\s synchronize, the `Driver` clears each `sync_event`.
        send_event : threading.Event
            Global connection/socket sending :class:`~threading.Event` controlled
            by the parent :class:`~.Driver`.  Until this :class:`~threading.Event`
            is set, we withhold the final few bytes of all sent data.
            When set, it indicates the remaining buffered data may be sent.
        read_event : threading.Event
            Global connection/socket reading :class:`~threading.Event` controlled
            by the parent :class:`~.Driver`.
            When set, it indicates that `Connection`\s may read server responses.

            .. note::
                Due to CPython's Global Interpreter Lock, only one thread can execute
                Python bytecode at a time.  The lock is only guaranteed to be released
                during I/O, but that means some threads may begin fetching a
                :class:`~requests.Response` before others have finished sending their
                :class:`~requests.Request`.
                To prevent this, all threads must complete their sends before reading any results.
        connect_mode : {'normal', 'same', 'random', 'different'}, optional
            Determines how the hostname's server IP address is chosen:

            - Normal: always call :func:`~socket.getaddrinfo` and use what it returns.
              The results are usually similar but may vary from call to call.
            - Same: globally cache the :func:`~socket.getaddrinfo` result and use it.
              This ensures that each `Connection` across all :class:`~.Thread`\s
              use the same IP address.
            - Random: randomize which IP address each `Connection` connects to.
            - Different: each `Connection` should connect to a different IP address.
              The :func:`~socket.getaddrinfo` result is chosen based on the
              `Connection`'s :attr:`thread_num`.  If there are fewer IP addresses
              than threads, the selection wraps around.

            Default is ``same``.

            .. note::
                The :attr:`connect_mode` argument isn't foolproof.
                If the connection to the preferred IP address fails, it will try
                the remaining IP addresses until a successful connection is made
                (this is the default behavior of :func:`~socket.create_connection`).
                This means that ``diff`` mode can never fully guarantee that each
                `Connection` actually connects to a different IP address.


    Attributes
    ------------
    race_args : dict
        Local copy of `__init__` parameter.

    thread_num : int
        Unpacked value from :attr:`race_args`.
    shared : dict
        Unpacked value from :attr:`race_args`.
    sync_event : Event
        Unpacked value from :attr:`race_args`.
    send_event : Event
        Unpacked value from :attr:`race_args`.
    read_event : Event
        Unpacked value from :attr:`race_args`.

    logger : logging.Logger
        A :class:`logging.Logger` instance for this `Connection`.

    _send_buffer : str
        Whenever :meth:`~.send` is called, the data is appended to this buffer.
        If this buffer is over :attr:`_buffer_size` bytes long, all but the
        final :attr:`_buffer_size` bytes are sent.

    _buffer_size : int
        Defines the maximum length of :attr:`_send_buffer` before flushing occurs.
    """

    def __init__(self, *args, **kwargs):
        self.race_args = kwargs.pop('race_args', {})
        super(BaseConnection, self).__init__(*args, **kwargs)

        # Required arguments
        self.thread_num = self.race_args['thread_num']
        self.shared     = self.race_args['shared']
        self.sync_event = self.race_args['sync_event']
        self.send_event = self.race_args['send_event']
        self.read_event = self.race_args['read_event']

        # Optional arguments
        self.connect_mode = self.race_args.get('connect_mode', 'same').lower()

        self.logger = _LOG.getChild("C{:03d}".format(self.thread_num))

        self._send_buffer = ""
        self._buffer_size = 2


    def getaddrinfo(self, host, port):
        """A thread-safe, caching version of :func:`~socket.getaddrinfo`."""
        host_port = (host, port)

        with _gai_lock:
            addrs, timestamp = _gai_cache.get(host_port, ([], 0))

            if not addrs or (time.time() - timestamp) > _gai_expiry:
                # Missing or expired results, get latest address info.
                family = urllib3.util.connection.allowed_gai_family()
                addrs = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)

            _gai_cache[host_port] = (addrs, time.time())
            return addrs


    def _new_conn(self):
        """Returns a connection object for our :attr:`host` and :attr:`port`."""
        mode = self.connect_mode

        if not mode or mode.startswith("norm"):
            # "Normal" mode, each thread does its own `getaddrinfo`
            # and may connect to the same or different host IP addresses.
            addrs = socket.getaddrinfo(self.host, self.port)

        else:
            # For all other modes, use cached results if available.
            addrs = self.getaddrinfo(self.host, self.port)

        if mode.startswith("diff"):
            # "Different" mode, each thread uses a different host IP.
            # The `thread_num` is used to rotate the IP address list.
            shift = self.thread_num % len(addrs)
            addrs = addrs[shift:] + addrs[:shift]

        elif mode.startswith("rand"):
            # "Random" mode, each thread connects to a random host IP.
            addrs = random.sample(addrs, len(addrs))

        elif mode.startswith("same"):
            # "Same" mode, each thread connects to the same host IP.
            # The IP addresses are already in a constant order due to caching.
            pass

        elif not mode.startswith("normal"):
            self.logger.warn("Unrecognized connect mode: {}".format(mode))

        # The base `_new_conn` method uses `host` and `port` directly.
        # Typically `host` is a domain name, but IP addresses work too.
        # To force the host IP address, we must clobber and restore `host`.
        orig_host = self.host
        orig_port = self.port

        conn = None
        for connect_info in addrs:
            # Try each address entry until a successful connection is made.
            family, socktype, proto, name, server = connect_info
            self.host, self.port = server

            try:
                conn = super(BaseConnection, self)._new_conn()
                break
            except socket.error as error:
                last_error = error

        # Reverting to pre-clobbered values.
        # This is crucial because HTTPS uses `host` as the SNI.
        self.host = orig_host
        self.port = orig_port

        if conn:
            self.logger.info("Connected to {}".format(conn.getpeername()))
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return conn
        else:
            raise last_error


    def send(self, data, flush = False):
        """Sends all data except for a the last few bytes until flushed."""
        self._send_buffer += data
        to_send = ""

        if flush:
            # If `send_event` is set or we're being forced to flush, send everything we have.
            to_send += self._send_buffer
            self._send_buffer = ""

        if len(self._send_buffer) > self._buffer_size:
            # If the sending buffer is oversized, send all but the final few bytes and trim it.
            to_send += self._send_buffer[:-self._buffer_size]
            self._send_buffer = self._send_buffer[-self._buffer_size:]

        if to_send:
            # Despite it's name, the underlying class uses `sendall`.
            super(BaseConnection, self).send(to_send)


    def getresponse(self, **kwargs):
        """Flushes all buffered data and returns the server response after :attr:`read_event` is set."""

        # We aren't ready to flush until we're certain our socket is writable.
        select([], [self.sock], [])

        self.sync_event.set()
        self.send_event.wait()
        self.send("", flush = True)

        # All threads must finish sending data before any thread begins reading data.
        # The cPython global interpreter will release on I/O, but makes no guarantees otherwise.
        # To prevent any thread from getting ahead of the rest, we enforce a sync here.
        self.sync_event.set()
        self.read_event.wait()
        return super(BaseConnection, self).getresponse(**kwargs)


# Applying the same modifications to the default `HTTP[S]Connection` classes.
# The default HTTPS class accepts different keyword arguments and applies socket wrapping and SSL context.
# Instead of making one "uber" class to handle both HTTP/HTTPS, we dynamically inherit from each of them.
# Note: due to how `super()` works, order of inheritance matters.
class HTTPConnection(BaseConnection, urllib3.connection.HTTPConnection):
    pass

class HTTPSConnection(BaseConnection, urllib3.connection.HTTPSConnection):
    pass