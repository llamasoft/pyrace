"""Provides a custom :class:`~.Thread` to mount and interact with :class:`~.HTTPAdapter`\s.

Multiple :class:`~.Thread`\s are driven by a single :class:`~.Driver`.
Each :class:`~.Thread` is responsible for:

1. Creating and maintaining a :class:`~requests.Session` object.
2. Mounting a custom adapter (i.e. our :class:`~.HTTPAdapter`) to the :class:`~requests.Session`.
3. Extracting cookies from outgoing :class:`~requests.Request`\s into a cookie jar.
4. Optionally evaluating statements embedded in :class:`~requests.Request`\s.
5. Maintaining a :obj:`work_queue` of :class:`~requests.Request`\s or callables to execute.

"""
import logging
import re
import requests
import threading

from copy import copy
from six.moves import urllib_parse as urlparse

from requests.exceptions import RequestException
from requests.packages.urllib3.exceptions import HTTPError

from .adapter import HTTPAdapter

# Convenience imports; for use by evaluated statements
import base64, binascii, datetime, hashlib, json, math, random, time


_LOG = logging.getLogger(__name__)


class InvalidWorkItem(Exception):
    pass


class Thread(threading.Thread):
    """
    A worker thread that acts as the middleman between :class:`~.Driver`\s
    and :class:`~.HTTPAdapter`\s.


    Parameters
    ------------
    work_queue : list
        A list of work items for this class to process when :meth:`~.Thread.run` is executed.
        Work items *must* be a :class:`requests.Request` or a callable function:

        - :class:`~requests.Request`\s are sent and their :class:`~requests.Response`\s
          are appended to the :attr:`all_responses` list.
        - Functions will be executed with the :class:`~.Thread` instance as the
          only parameter (i.e. :obj:`self`).  Functions are encouraged inspect the
          :class:`~.Thread` state, process any responses, and to modify
          :attr:`work_queue` to add or change work as necessary.

    race_args : dict
        Arguments for this class and its child :class:`~.BaseConnection`\s.
        Entries relevant to this class are:

        thread_num : int
            The thread number associated with this :class:`~.Thread` and its children classes.
        shared : dict
            A shared dict between this :class:`~.Thread`, its :class:`Driver`, and its children classes.
        send_kwargs : dict, optional
            Dict of extra arguments to pass to :meth:`requests.Session.send`.
            Default is ``{}``.
        fake_send : bool, optional
            Don't actually send the :class:`~requests.Request`, just create a fake
            :class:`~requests.Response` from it.  The :class:`~requests.PreparedRequest`
            is stored in :attr:`requests.Response.request`.  Useful for debugging.
            Default is ``False``.
        do_eval : bool, optional
            Indicates if embedded statements in :class:`~requests.Request`\s should be evaluated.
            :class:`~requests.Request`\s are evaluated before being :meth:`requests.Session.prepare`\d.
            See :attr:`_eval_attrs`, :attr:`_eval_pattern`, and :attr:`_eval_action` for details.
            Default is ``False``.
        save_sent_cookies : bool, optional
            Cookies manually set in :class:`~requests.Request` :attr:`headers` or :attr:`cookie`
            attributes should be extracted and saved in our :class:`~requests.Session`'s cookie jar.
            Extraction occurs after embedded statement evaluation is applied.
            Default is ``True``.


    Attributes
    ------------
    work_queue : list
        Local copy of `__init__` parameter.
    race_args : dict
        Local copy of `__init__` parameter.

    thread_num : int
        Unpacked value from :attr:`race_args`.
    shared : dict
        Unpacked value from :attr:`race_args`.
    fake_send : bool
        Unpacked value from :attr:`race_args`.
    do_eval : bool
        Unpacked value from :attr:`race_args`.
    save_sent_cookies : bool
        Unpacked value from :attr:`race_args`.

    logger : logging.Logger
        A :class:`~logging.Logger` instance for this :class:`~.Thread`.

    _eval_attrs : list
        The list of :class:`~requests.Request` attributes to apply :attr:`_eval_pattern` to.
    _eval_pattern : str
        The regex pattern that searches for evaluable code in the prepared request attributes.
        Default pattern matches ``<<<statement_goes_here>>>``.
    _eval_flags : int
        The regex flags to apply to :attr:`_eval_pattern`.
        Default is ``re.VERBOSE | re.DOTALL``.
    _eval_action : callable
        The action to take with the :class:`re.MatchObject` found by :attr:`_eval_pattern`.
        Default is converting :class:`re.MatchObject` group 1 to a string, then :func:`eval` it.

    session : requests.Session
        The session-level storage associated with the most recent :meth:`~.run` call.
        The :class:`~requests.Session` is created when :meth:`.run` begins and is closed when it ends.

    adapter : pyrace.HTTPAdapter
        The adapter responsible for handling our :class:`~requests.Session`'s HTTP requests.
        See :ref:`transport adapter <requests:transport-adapters>` documentation for details.

    response : requests.Response
        The :class:`~requests.Response` object from the most recently executed :class:`~requests.Request`.

    all_responses : list
        All :class:`~requests.Response` objects from the most recent :meth:`~.run` call, in order.


    Raises
    --------
    InvalidWorkItem
        A work item in :attr:`work_queue` wasn't a :class:`~requests.Request` or callable.
    """

    _eval_attrs = [
        'url',
        'headers',
        'cookies',
        'params',
        'data',
        'json',
    ]
    _eval_pattern = r'<<< (.*?) >>>'
    _eval_flags   = re.VERBOSE | re.DOTALL
    _eval_action  = lambda self, match: str(eval(match.group(1)))


    def __init__(self, work_queue, race_args):
        """Creates a :class:`~.Thread` with arguments for itself and its :class:`~.BaseConnection`\s."""
        self.work_queue = work_queue
        self.race_args  = race_args

        # Shared parameters
        self.thread_num = self.race_args['thread_num']
        self.shared     = self.race_args['shared']

        # Thread exclusive parameters
        self.send_kwargs       = self.race_args.pop('send_kwargs', {})
        self.do_eval           = self.race_args.pop('do_eval', False)
        self.fake_send         = self.race_args.pop('fake_send', False)
        self.save_sent_cookies = self.race_args.pop('save_sent_cookies', True)

        # Convert a non-list work_queue into a single-element list.
        if not isinstance(self.work_queue, list):
            self.work_queue = [self.work_queue]

        # Fail early if an invalid work item is detected.
        # This prevents a multitude of runtime exceptions when the threads run.
        self._validate_work_queue(self.work_queue)

        self.logger = _LOG.getChild("T{:03d}".format(self.thread_num))

        self.session       = None
        self.adapter       = None
        self.response      = None
        self.all_responses = []

        super(Thread, self).__init__()
        self.daemon = True


    def _validate_work_queue(self, work_queue):
        """Ensures that all :attr:`work_queue` items are :class:`~requests.Request`\s or callables."""
        for i, work_item in enumerate(work_queue):
            if callable(work_item):
                pass
            elif isinstance(work_item, requests.Request):
                pass
            else:
                raise InvalidWorkItem("Work item {} isn't callable or Request: {}".format(i, work_item))


    def _create_session(self):
        """Creates a :class:`~requests.Session` and overrides default headers."""
        session = requests.Session()

        # Prevent the fall-back "python-requests/version" User-Agent header.
        # We still allow the following default headers:
        # - Accept-Encoding: gzip, deflate
        # - Accept: */*
        # - Connection: keep-alive
        session.headers['User-Agent'] = None
        return session


    def _get_adapter(self, race_args):
        """Creates a new instance of our :class:`~.HTTPAdapter` with :attr:`race_args`."""
        return HTTPAdapter(race_args = race_args)


    def _mount_adapter(self, session, adapter):
        """Mount an :class:`~.HTTPAdapter` to the given :class:`~requests.Session`."""
        session.mount("http://",  adapter)
        session.mount("https://", adapter)


    def _prepare_request(self, session, request):
        """Create a :class:`~requests.PreparedRequest` under the current :class:`~requests.Session`."""
        return session.prepare_request(request)


    def _eval_request_attrs(self, req, attrs):
        """Evaluates statements in the attributes of a :class:`~requests.Request`, returning a new one."""

        # Shallow copy suffices.
        # `_eval_recursive` creates new objects while it recurses,
        # so there's no risk of damaging the original copies.
        rtn = copy(req)

        for attr in attrs:
            if hasattr(req, attr):
                prepped_attr = getattr(req, attr)
                evaluated_attr = self._eval_recursive(prepped_attr)
                if evaluated_attr != prepped_attr:
                    setattr(rtn, attr, evaluated_attr)
            else:
                self.logger.warn("{} has no {} attribute to evaluate".format(req, attr))

        return rtn


    def _eval_recursive(self, thing):
        """Recursively evaluates statements within an object, returning a new object of the same type."""
        if isinstance(thing, dict):
            return {key: self._eval_recursive(value) for (key, value) in thing.items()}

        elif isinstance(thing, list):
            return [self._eval_recursive(value) for value in thing]

        elif isinstance(thing, tuple):
            return (self._eval_recursive(value) for value in thing)

        elif isinstance(thing, str):
            # The bottom of the recursion stack, actually applies `_eval_action` to the string.
            # The matched pattern will be replaced with its evaluated result.
            return re.sub(
                self._eval_pattern,
                self._eval_action,
                thing,
                flags = self._eval_flags
            )

        else:
            # Unknown type, return it as-is (objects, numerics, None, etc)
            return thing


    def _extract_cookies(self, req, jar = None):
        """
        Extracts cookies from a :class:`~requests.Request` and returns them
        in a :class:`~requests.RequestsCookieJar`.

        Arguments
        -----------
        req : requests.Request
            The :class:`~requests.Request` that the cookies should be extracted from.
            If a Cookie header is present, it will be used.
            If not, the `cookie` attribute will be used instead.
        jar : requests.RequestsCookieJar, optional
            The :class:`~requests.RequestsCookieJar` to add the cookies to.
            Only cookies with differing values will be added to prevent domain/path issues.
            Default is ``None``, create a new :class:`~requests.RequestsCookieJar`.
        """
        if not jar:
            cookie_jar = requests.cookies.RequestsCookieJar()
        else:
            cookie_jar = jar.copy()

        # Get the Request's host so we can tie the cookies to it.
        # This may be more restrictive than required (i.e. subdomain instead of host)
        # but much less likely to send cookies to places they shouldn't go.
        domain = getattr(urlparse.urlparse(req.url), 'netloc', None)

        cookie_tuples = []

        # Cookie header takes precedence over cookie dict.
        # This is how the requests library handles it as well.
        cookie_header = req.headers.get("Cookie", None)
        if cookie_header:
            for cookie in cookie_header.split(";"):
                if not "=" in cookie:
                    # Cookies must have a name and a value as per RFC 6265:
                    # https://stackoverflow.com/a/23393248/477563
                    self.logger.warn("Cookie header entry '{}' missing a '='".format(cookie))
                    continue

                name, value = [part.strip() for part in cookie.split("=", 1)]
                cookie_tuples.append( (name, value) )

        elif req.cookies:
            for name, value in req.cookies.items():
                cookie_tuples.append( (name, value) )

        # If a cookie with this name and value exists, don't update it.
        # The existing cookie may have more accureate domain/path info than we do.
        for name, value in cookie_tuples:
            if cookie_jar.get(name, domain = domain) != value:
                cookie_jar.set(name, value, domain = domain)

        return cookie_jar


    def _send_request(self, session, prepared, **send_kwargs):
        """
        Sends (or pretends to send) a :class:`~requests.PreparedRequest` under
        our :class:`~requests.Session`, returning a :class:`~requests.Response`.
        """
        if self.fake_send:
            response = requests.Response()
            response.request = prepared
        else:
            response = session.send(prepared, **send_kwargs)

        return response


    def run(self):
        """
        The work body of a :class:`threading.Thread`.
        Processes work items from :attr:`work_queue` in sequential order.
        """
        self.session = self._create_session()
        self.adapter = self._get_adapter(self.race_args)
        self._mount_adapter(self.session, self.adapter)
        self.all_responses = []

        while self.work_queue:
            self.logger.debug("Work queue size: {}".format(len(self.work_queue)))
            work_item = self.work_queue.pop(0)

            if callable(work_item):
                # A callable work item that may do result processing and/or modify `work_queue`.
                work_item(self)
                self._validate_work_queue(self.work_queue)
                continue

            # The Request must be prepared under our current Session to use its state.
            # This includes using the custom persistent cookies, headers, etc.
            # This also gives us an opportunity to modify the data before sending...
            request = work_item

            # ... like evaluating embedded Python statements in the URL, headers, and data.
            if self.do_eval:
                request = self._eval_request_attrs(request, self._eval_attrs)

            # Cookie header to CookieJar extraction must happen after eval as headers may have changed.
            # The requests library doesn't save sent Cookie header or dict entries into the CookieJar.
            # If we didn't extract them manually, the first request would have the correct Cookie header,
            # but subsequent requests/redirects will only have the response's Set-Cookie values.
            # As a note, if a Cookie header and CookieJar are both present, the header is used verbatim.
            if self.save_sent_cookies:
                self.session.cookies = self._extract_cookies(request, jar = self.session.cookies)

            # Tying our Session cookies to the Request.
            # This also maps data structures (e.g. files, cookies, data) into real strings.
            prepared = self._prepare_request(self.session, request)

            try:
                # Get a Response for our PreparedRequest
                self.response = self._send_request(self.session, prepared, **self.send_kwargs)

            except (RequestException, HTTPError) as ex:
                # If something HTTP related went wrong, save the exception as the response.
                # This will give the Driver something to inspect when the Thread dies.
                self.response = ex
                self.session.close()
                raise ex

            finally:
                # Responses contain the PreparedRequest that was sent, no need to store it separately.
                self.all_responses.append(self.response)

        self.logger.debug("Work queue empty, shutting down")

        # Closes the Session and all of its adapters and their children.
        self.session.close()