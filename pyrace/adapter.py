"""
Provides a custom :class:`~requests.HTTPAdapter` that uses our :class:`~.HTTPConnectionPool`.

This :class:`~requests.HTTPAdapter` does two very important things:

1. It makes the default :class:`urllib3.PoolManager` use our :class:`~.HTTPConnectionPool`\s instead.
   These :class:`~.HTTPConnectionPool`\s are what allow us to use our :class:`~.HTTPConnection`\s.
2. It smuggles :attr:`race_args` to our :class:`~.HTTPConnection` class.
   The default :class:`~requests.HTTPAdapter` fails if extra keyword arguments are supplied,
   so we have to remove and re-inject :attr:`race_args` at the correct locations.
"""

import logging
import requests

from .connectionpool import HTTPConnectionPool, HTTPSConnectionPool


_LOG = logging.getLogger(__name__)


class HTTPAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        # The real HTTPAdapter's __init__ doesn't accept extra keywords, but init_poolmanager does.
        # Extract our keywords here, then re-add during init_poolmanager.
        self.race_args = kwargs.pop('race_args', {})

        self.thread_num = self.race_args.get('thread_num', 0)
        self.logger = _LOG.getChild("A{:03d}".format(self.thread_num))

        # Calls self.init_poolmanager() towards the end.
        super(HTTPAdapter, self).__init__(*args, **kwargs)


    def init_poolmanager(self, *args, **pool_kwargs):
        """Creates a :class:`~urllib3.PoolManager` that this :class:`~.HTTPAdapter`
        gets :class:`~.HTTPConnectionPool`\s from.

        Notes
        -------
        Every :class:`requests.HTTPAdapter` is responsible for maintaining a
        :class:`urllib3.PoolManager`.  The :class:`~urllib3.PoolManager` is
        responsible for maintaining a `ConnectionPool` for each scheme.
        The `ConnectionPool`\s are responsible for maintaining `Connection` objects.

        To pass :attr:`race_args` to our :class:`~.HTTPConnection` initialization,
        the following must take place:

        1. Inject :attr:`race_args` into :attr:`pool_kwargs`.
        2. Initialize a :class:`~urllib3.PoolManager` with ``**pool_kwargs`` which
           will save any unrecognized keyword arguments in :attr:`connection_pool_kw`.
        3. Change the :class:`~urllib3.PoolManager`'s `ConnectionPool` class
           references to pint to our custom `ConnectionPool`\s instead.
        4. When :class:`~urllib3.HTTPConnectionPool` is initialized with ``**connection_pool_kw``,
           it saves any unrecognized keyword arguments in :attr:`conn_kw`.
           (`ConnectionPool`\s are created the first time a `Connection` is needed for a scheme.)
        5. When a :class:`urllib3.Connection` is created, it is initialized with
           ``**conn_kw`` (which now contains a :obj:`race_args` key).
        """

        # 1. Inject race_args into pool_kwargs.
        pool_kwargs['race_args'] = self.race_args

        # 2. Initialize a PoolManager with **pool_kwargs which
        #    will save any unrecognized keyword arguments in connection_pool_kw.
        super(HTTPAdapter, self).init_poolmanager(*args, **pool_kwargs)

        # 3. Change the :class:`~urllib3.PoolManager`'s `ConnectionPool` class
        #    references to pint to our custom `ConnectionPool`\s instead.
        # Cloning pool_classes_by_scheme to a new dict is required because
        # it was created at the class level, not the instance level.
        old_classes = self.poolmanager.pool_classes_by_scheme
        new_classes = old_classes.copy()
        new_classes['http']  = HTTPConnectionPool
        new_classes['https'] = HTTPSConnectionPool
        self.poolmanager.pool_classes_by_scheme = new_classes

        # 3. (Continued) urllib3 v1.21 changed how the default pool key creation function works.
        # It now considers the *whole* collection of keyword arguments instead of just host/scheme.
        # If we don't exclude race_args from the key function, it will fail to instantiate the
        # namedtuple because it will supplied a keyword argument it wasn't expecting.
        def patch_pool_key_fn(fn):
            def patch(request_context):
                # Copying and removing race_args from the context
                patched_context = request_context.copy()
                patched_context.pop('race_args')

                # Calling the original pool key function with the patched context
                fn(patched_context)

            return patch

        old_key_fns = self.poolmanager.key_fn_by_scheme
        new_key_fns = old_key_fns.copy()
        new_key_fns['http']  = patch_pool_key_fn(old_key_fns['http'] )
        new_key_fns['https'] = patch_pool_key_fn(old_key_fns['https'])
        self.poolmanager.key_fn_by_scheme = new_key_fns