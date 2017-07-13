Quick Start
=============


Installation
--------------

From PyPI::

    pip install pyrace

From GitHub::

    git clone https://github.com/llamasoft/pyrace.git
    cd pyrace
    python setup.py install


Basic Usage
-------------

To get pyrace up and running, all you need is a :class:`~.Driver` and a :obj:`work_queue`.

- The :obj:`work_queue` defines the :class:`~requests.Request`\s that each :class:`~.Thread` should execute.
- The :class:`~.Driver` creates the :class:`~.Thread`\s and drives them through
  their :obj:`work_queue`\s in a synchronized manner.

The following is taken from :file:`examples/basic.py`:

.. literalinclude:: ../examples/basic.py


Regarding Thread Count
~~~~~~~~~~~~~~~~~~~~~~~~
**Less is more when it comes to the number of parallel threads!**

Using too many threads may yield inconsistent results.  This library *sends*
requests as precise as possible, but networks can interfere with when the
requests are *received* by the target server. Typically, request timing follows
a normal distribution; most requests arrive very close together, but a few may
arrive early and a few may arrive late.

Knowing this, choose your :obj:`thread_count` value accordingly:

If the target is meant to allow an action *once* (e.g. sending items, deleting a
post), then successful race condition exploitation only depends on the timing of
the *first few* requests. Using a large number of threads increases the chance
that a request to arrive too early, preventing the other requests from having an
effect. In these situations, you should only use *two or three* threads.

If the target is meant to allow an action *multiple times* (e.g. returning
search results, uploading a file) then successful race condition exploitation
only depends on the timing of *any two* requests. A large number of parallel
requests may result in variability, but due to the tendancy for requests to
arrive in groups, the chance of any two requests colliding increases. In these
situations, the number of threads depends mainly on your network connection. A
thread count between *four and ten* is reasonable but more may be used if your
network allows.

.. note::
    Be careful to not use too many threads as your burst of requests may
    result in (or be viewed as) a denial of service attack.


Advanced Usage
----------------

Keyword Arguments
~~~~~~~~~~~~~~~~~~~

pyrace supports passing custom parameters to the :class:`~.Thread` and :class:`~.BaseConnection`
classes by providing extra keyword arguments to the :meth:`~.Driver.process` method.
These keywords are passed to the classes via :obj:`race_args`.

do_eval:
    Evaluates statements embedded in :class:`~requests.Request` fields.
    See :file:`examples/eval.py` for example usage.
save_sent_cookies:
    Saves user-defined :class:`~requests.Request` cookies to the current :class:`~requests.Session`.
    See :file:`examples/cookies.py` for example usage.
send_kwargs:
    Dict of extra arguments to pass to :meth:`requests.Session.send`.
    See linked documentation's source code for all possible values.
    Common values include :obj:`verify` and :obj:`proxies`.
connect_mode:
    Determine which IP address threads connect to for a given hostname.
    If a hostname resolves to multiple IP addresses, this allows you to specify that
    all threads should connect to the same, different, or random IP addresses.
    See :file:`example/timing.py` for example usage.

For a full list of valid :obj:`race_args` keywords, or for additional details
on the above keywords, see :class:`~.Thread` and :class:`~.BaseConnection`
documentation.


Callbacks
~~~~~~~~~~~

In addition to :class:`~requests.Request`\s, the :obj:`work_queue` also supports callable functions.
These functions are passed a single argument: the calling :class:`~.Thread` instance (i.e. `self`).
This gives the user total control over the :class:`~.Thread`, allowing you to do such things as:

- Dynamically adding new :class:`~requests.Request`\s to the :class:`~.Thread`'s
  :obj:`work_queue` based on previous :class:`~requests.Response`\s.
- Modifying the :class:`~.Thread`'s :class:`~requests.Session` to edit headers or cookies.
- Literally anything a :class:`~.Thread` can do, you can control using callable functions.

For an example of callbacks in action, see :file:`example/callbacks.py`.