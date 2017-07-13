Developer Reference
=====================

Technique
-----------

What makes pyrace special is its ability to land multiple HTTP[S] requests in the smallest possible
time frame. The technique used to accomplish this is rather straightforward:

1. Create multiple threads.
2. Allow the threads send all but the final few bytes of their data.
3. Force the threads to synchronize using :class:`~threading.Event`\s.
4. Allow the threads to send their final bytes, completing all requests simultaneously.

This technique relies on the fact that a request isn't *received*
by a server until the entirety of the request arrives.
In practice, this means we only need to synchronize the arrival of
the *final* bytes of requests, not the bulk of their contents.
For implementation details, see the :class:`~.BaseConnection` documentation.

**If the technique is so simple, why does this module have so many classes?**

The primary classes are :class:`~.Driver`, :class:`~.Thread`,
and :class:`~.HTTPConnection`, but they are separated by many layers of abstraction.
Communication between the classes is acheived using the :obj:`race_args` object,
but the classes are separated by multiple layers, as shown below.  To pass :obj:`race_args`
to the primary classes, the intermediate classes must be modified or overwritten.

For example, in order to pass :obj:`race_args` to an :class:`~.HTTPConnection`,
we must control its parent :class:`~urllib3.HTTPConnectionPool`.  
To control an :class:`~urllib3.HTTPConnectionPool`, we must also control its
parent :class:`~urllib3.PoolManager`. So on and so forth.


Class Relationships
---------------------
Overriding connection classes at a session level requires modifying many of the classes in between.
Here is a diagram illustrating how :mod:`pyrace` (and :mod:`requests`/:mod:`urllib3`)
classes interact with each other:

::

           pyrace.Driver
                /|\
               V V V
           pyrace.Thread
                 |
                 V
          requests.Session
                 |
                 V
         pyrace.HTTPAdapter
                 |
                 V
        urllib3.PoolManager
                /|\
               V V V
    pyrace.HTTP[S]ConnectionPool
                /|\
               V V V
      pyrace.HTTP[S]Connection

All of the classes from :class:`~requests.Session` to :class:`~.HTTPConnection` required
modification in some way, but only :class:`~.HTTPAdapter`, :class:`~.HTTPConnectionPool`, and
:class:`~.HTTPconnection` had to be overridden.
The other classes, :class:`~requests.Session` and :class:`~urllib3.PoolManager`,
could be modified on a per-instance basis.


Class Summaries
-----------------

pyrace.Driver
~~~~~~~~~~~~~~~
A :class:`~.Driver` has one or more :class:`~.Thread`\s.

The :class:`~.Driver` is responsible for creating :class:`~.Thread`\s, providing them with a
:obj:`work_queue`, and driving them through their respective workloads.  The :obj:`work_queue` is a
list of :class:`~requests.Request`\s and callable functions to be run.  Driving is accomplished by
using :class:`~threading.Event`\s to indicate when :class:`~.Thread` :class:`~.BaseConnection`\s
should synchronize, finish sending data, or begin reading responses.


pyrace.Thread
~~~~~~~~~~~~~~~
A :class:`~.Thread` has a single :class:`~requests.Session` and a single :obj:`work_queue`.
The :class:`~.Thread` handles creation of a :class:`~requests.Session` and processing
:obj:`work_queue` entries.

A :class:`~requests.Session` is created in order to:

- Persist data (e.g. cookies) across requests within the :obj:`work_queue`.
- Allow a custom :class:`~.HTTPAdapter` to be mounted to handle HTTP[S] requests.

Processing :obj:`work_queue` entries includes:

- Sending :class:`~requests.Request`\s.
- Executing callable functions within the :class:`~.Thread`'s context.
- Optionally extracting outgoing request cookies to the :class:`~requests.Session` cookie jar.
- Optionally evaluating embedded statements within outgoing requests.


requests.Session
~~~~~~~~~~~~~~~~~~
A :class:`~requests.Session` has one or more :class:`~.HTTPAdapter`\s to handle per-service configurations.
:class:`~requests.Session`\s persist data across multiple :class:`~requests.Request`\s
and allow for mounting custom :class:`~.HTTPAdapter`\s.

This :class:`~requests.Session`'s parent :class:`~.Thread` will mount a custom
:class:`~.HTTPAdapter` to handle HTTP[S] requests.

For more information, see :ref:`session object <requests:session-objects>` documentation.


pyrace.HTTPAdapter
~~~~~~~~~~~~~~~~~~~~
An :class:`~.HTTPAdapter` has a single :class:`~urllib3.PoolManager`.  
Transport adapters control the interaction with other services (i.e. HTTP[S]).

An instance of this class will be mounted to our parent :class:`~.Thread`'s :class:`~requests.Session`.
One instance will handle both HTTP and HTTPS requests.

This is a minimally modified version of :class:`requests.HTTPAdapter`.
The modifications include:

- Allow for the passing arguments (i.e. :obj:`race_args`) to all children classes.
- Replacing the :class:`~urllib3.PoolManager`'s :class:`~.HTTPConnectionPool` references.
  This allows for the (eventual) usage of our custom :class:`~.HTTPConnection` class.

For implementation details, see :class:`~.HTTPAdapter` documentation.
For general information, see :ref:`transport adapter <requests:transport-adapters>` documentation.


urllib3.PoolManager
~~~~~~~~~~~~~~~~~~~~~
A :class:`~urllib3.PoolManager` has one or more :class:`ConnectionPool`\s, one for each scheme
(i.e. HTTP/HTTPS).  When an :class:`~.HTTPConnection` is required for a given scheme, the
:class:`~urllib3.PoolManager` routes the request to the correct :class:`~.HTTPConnectionPool`.

This :class:`~urllib3.PoolManager`'s parent :class:`~.HTTPAdapter` will modify
the :class:`~.HTTPConnectionPool` class references used during creation of new
:class:`~.HTTPConnectionPool`\s.

For more information, see :class:`urllib3.PoolManager` documentation.


pyrace.HTTP[S]ConnectionPool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
An :class:`~.HTTPConnectionPool` has one or more :class:`~.HTTPConnection`\s.  
When an :class:`~.HTTPAdapter` requests a connection, the :class:`~.HTTPConnection` will
return one from its pool or create a new one.  Because HTTP and HTTPS connections
are incompatible due to SSL wrapping, the two are kept separate.

This is a minimally modified version of :class:`urllib3.HTTPConnectionPool`.
The modification changes the :obj:`ConnectionCls` value for HTTP and HTTPS.


pyrace.HTTP[S]Connection
~~~~~~~~~~~~~~~~~~~~~~~~~~
An :class:`~.HTTPConnection` has a single :class:`~socket.Socket`.  
The :class:`~.HTTPConnection` handles creating a connection and sending/receiving raw data.
This is where the bulk of the Technique_ is implemented.

This is a modified version of :class:`urllib3.connection.HTTPConnection`.
The modifications include:

- Accepting arguments from the parent :class:`~.Driver` (via :obj:`race_args`).
- Withholding the final few bytes of all sent data until an :class:`~threading.Event` is set.
- Optionally manipulating which of the host's IP address to connect to.