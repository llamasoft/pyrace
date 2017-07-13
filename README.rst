pyrace
========

.. image:: https://readthedocs.org/projects/pyrace/badge/?version=latest
    :target: http://pyrace.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

pyrace is an HTTP[S] race condition testing package built using the `Requests`_ library.

For for usage information, developer reference, or technical details, please see the `online documentation`_.

.. _Requests: http://docs.python-requests.org/en/master/
.. _online documentation: https://pyrace.readthedocs.io/


Installing
------------

From PyPI::

    pip install pyrace

From GitHub::

    git clone https://github.com/llamasoft/pyrace.git
    cd pyrace
    python setup.py install


Examples
----------
Single request per worker::

    >>> driver = pyrace.Driver()
    >>> request = requests.Request('GET', 'http://now.httpbin.org')
    >>> threads = driver.process(request, thread_count = 2)
    >>> [t.response.json()['now']['epoch'] for t in threads]
    [1497300394.5125718, 1497300394.5126784]

Multiple requests per worker::

    >>> driver = pyrace.Driver()
    >>> req1 = requests.Request('GET', 'http://httpbin.org/get?foo=bar')
    >>> req2 = requests.Request('POST', 'http://httpbin.org/post?baz=qux')
    >>> work_queue = [req1, req2]
    >>> threads = driver.process(work_queue, thread_count = 2)
    >>> [t.all_responses for t in threads]
    [[<Response [200]>, <Response [200]>], [<Response [200]>, <Response [200]>]]

Evaluation of embedded statements in requests::

    >>> driver = pyrace.Driver()
    >>> data = {'thread': '<<<self.thread_num>>>', 'rand': '<<<random.random()>>>'}
    >>> request = requests.Request('POST', 'http://httpbin.org/post', data = data)
    >>> threads = driver.process(request, thread_count = 2, do_eval = True)
    >>> [t.response.json()['form'] for t in threads]
    [{u'rand': u'0.405020220768', u'thread': u'0'}, {u'rand': u'0.466687005524', u'thread': u'1'}]

For more detailed demonstrations see the `examples subdirectory <examples/>`_.


License
---------
This project is licensed under the MIT License - see the `LICENSE.rst <LICENSE.rst>`_ file for details.


Acknowledgments
-----------------

* Kenneth Reitz for the Requests library
* Andrey Petrov for the urllib3 library that Requests builds upon
* andresriancho's `race-condition-exploit`_ project for inspiration

.. _race-condition-exploit: https://github.com/andresriancho/race-condition-exploit
