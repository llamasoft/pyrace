import logging
import threading
import requests
import time

from copy import deepcopy

from .thread import Thread


_LOG = logging.getLogger(__name__)

class Driver(object):
    """
    An interface to create :class:`~.Thread`\s, provide them with a work,
    and drive them through their work in a synchronized manner.

    Attributes
    ------------
    logger : logging.Logger
        A :class:`~logging.Logger` instance for this :class:`~.Driver`.
    send_event : threading.Event
        An :class:`~threading.Event` indicating that all connections should
        finish sending a :class:`~requests.Request`.
    read_event : threading.Event
        An :class:`~threading.Event` indicating that all connections should
        begin fetching a :class:`~requests.Response`.
    _thread_class : pyrace.Thread
        Our custom :class:`~.Thread` class.
        Exposed for easy injection of other custom classes.
    threads : list
        A list of :class:`~.Thread`\s from the most recent `process` call.
    """
    def __init__(self):
        self.logger = _LOG

        self.send_event = threading.Event()
        self.read_event = threading.Event()

        self._thread_class = Thread
        self.threads = []


    def create_threads(self, work_queue, thread_count, extra_args = {}):
        """
        Creates :class:`~.Thread`\s, initializing them with the provided :obj:`work_queue`
        and optional extra :obj:`race_args` keyword arguments.
        """
        self.logger.info("Spawning {} threads".format(thread_count))

        threads = []
        for n in xrange(thread_count):
            # A shared dict between us, a Thread instance, and its Connections.
            #
            # Due to the numerous layers of abstraction, there's no easy way to communicate with a
            # Connection object, even with access to the corresponding Session or Adapter.
            # To circumvent this, a dict is shared amongst all important classes within a Thread.
            # This dict is currently unused, but is provided for possible future extensions.
            shared = {}

            # Shared arguments for the Thread instance and its and Connections.
            # See Thread and Connection documentation for details.
            sync_event = threading.Event()
            race_args = {
                'thread_num': n,                # Shared
                'shared': shared,               # Shared
                'sync_event': sync_event,       # pyrace.Connection
                'send_event': self.send_event,  # pyrace.Connection
                'read_event': self.read_event,  # pyrace.Connection
            }

            # Extra arguments for the Thread instance and its Connections.
            # See Thread and Connection documentation for details.
            # Common examples are do_eval, fake_send, save_req_cookies, and connect_mode.
            race_args.update(extra_args)

            # It may be safe enough to shallow copy a Request, but I'd rather not risk it,
            # especially given that Threads may modify individual work_queue objects.
            new_thread = self._thread_class(deepcopy(work_queue), race_args)
            new_thread.sync_event = sync_event

            threads.append(new_thread)
            new_thread.start()

        return threads


    def _wait_for_sync(self, threads, timeout = None):
        """
        Waits until all :class:`~.Thread`\s have synchronized or terminated.

        Parameters
        ------------
        threads : list
            The list of :class:`~.Thread`\s that are being waited on.
        timeout : float, optional
            The maximum time in seconds to wait for all :class:`~.Thread`\s to become ready or terminate.
            If :obj:`timeout` is negative, zero, or ``None``, timing out is disabled.
            Default is ``None`` (wait as long as necessary).

        Returns
        ---------
        tuple
            A 3-tuple of lists of :class:`~.Thread`\s.
            In order, the tuple elements are:

            1. :obj:`ready_threads`, a list of :class:`~.Thread`\s that have set their :obj:`sync_event`.
            2. :obj:`pending_threads` a list of :class:`~.Thread`\s that have not yet
               set their :obj:`sync_event` within the time allotted by `timeout`.
            3. :obj:`dead_threads`, a list of :class:`~.Thread`\s that have completed or terminated.

        Notes
        -------
        The order of :class:`~.Thread`\s within the returned tuple's lists is not guaranteed
        to correspond to the ordering of the :obj:`threads` parameter.  The actual ordering
        depends on when :class:`~.Thread`\s terminated or synchronized.
        """
        start_time = time.time()

        ready_threads   = []
        pending_threads = threads
        dead_threads    = []

        while (pending_threads):
            elapsed_time = time.time() - start_time
            remaining_time = timeout - elapsed_time

            # Regardless of Thread states, stop on timeout.
            if timeout and timeout > 0 and elapsed_time > timeout:
                self.logger.warn("Timeout waiting for {} threads to sync".format(len(pending_threads)))
                break

            # Dynamically adjusted wait time based on how much time we have left.
            if timeout and timeout > 0:
                wait_time = len(pending_threads) / remaining_time
            else:
                wait_time = None

            # Checking each Thread for termination or synchronization.
            next_threads = []
            for thread in pending_threads:
                if thread.is_alive():
                    if thread.sync_event.wait(wait_time):
                        # Alive and synchronized.
                        ready_threads.append(thread)
                    else:
                        # Alive, but not synchronized.
                        next_threads.append(thread)
                else:
                    # He's dead, Jim.
                    dead_threads.append(thread)

            pending_threads = next_threads

        return (ready_threads, pending_threads, dead_threads)


    def drive_threads(self, threads, timeout = 10, send_delay = 0.10):
        """Drives a list of :class:`~.Thread`\s through their respective :obj:`work_queue`\s.

        Parameters
        ------------
        threads : list
            The list of :class:`~.Thread`\s to drive through their :obj:`work_queue`\s.
        timeout : float, optional
            How long to wait, in seconds, before considering a :class:`~.Thread` to have timed out.
            Timed out threads may continue to run, but are no longer driven directly or waited on.
            Default is ``10`` seconds.
        send_delay : float, optional
            How long to wait after syncing before allowing :class:`~.Thread`\s to finish sending data.
            Increasing this may improve timing precision by allowing sockets to fully flush.
            Increasing this value too much may result in connection timeouts.
            Default is ``0.10`` seconds.
        """
        active_threads = threads
        wave = 0

        while active_threads:
            # Order of actions:
            #
            # 1. Clear send_event and read_event
            # 2. Allow threads to send all but last two bytes, then sync
            # 3. Set send_event, allowing final two bytes to be sent
            # 4. Sync, waiting for all threads to finish sending
            # 5. Set read_event, allowing threads to read responses (and run callables)
            # 6. Sync, waiting for all threads to finish reading
            # 7. Prune all terminated threads from next iteration

            # 1. Clear send_event and read_event
            wave += 1
            self.logger.debug("Wave {} starting".format(wave))
            self.send_event.clear()
            self.read_event.clear()

            # 2. Allow threads to send all but last two bytes, then sync
            ready, pending, dead = self._wait_for_sync(active_threads, timeout)
            self.logger.debug(
                "Pre-send has {} Ready, {} Pending, {} Dead threads".format(
                    len(ready), len(pending), len(dead)
                )
            )
            for thread in ready: thread.sync_event.clear()
            if send_delay and send_delay > 0:
                time.sleep(send_delay)

            # 3. Set send_event, allowing final two bytes to be sent
            self.logger.debug("Setting send event")
            self.read_event.clear()
            self.send_event.set()

            # 4. Sync, waiting for all threads to finish sending
            ready, pending, dead = self._wait_for_sync(ready + pending, timeout)
            self.logger.debug(
                "Pre-read has {} Ready, {} Pending, {} Dead threads".format(
                    len(ready), len(pending), len(dead)
                )
            )
            for thread in ready: thread.sync_event.clear()

            # 5. Set read_event, allowing threads to read responses (and run callables)
            self.logger.debug("Setting read event")
            self.send_event.clear()
            self.read_event.set()

            # 6. Sync, waiting for all threads to finish reading
            ready, pending, dead = self._wait_for_sync(ready + pending, timeout)
            self.logger.debug(
                "Post-read has {} Ready, {} Pending, {} Dead threads".format(
                    len(ready), len(pending), len(dead)
                )
            )
            self.logger.info(
                "Wave {} result: {} threads completed, {} threads still alive".format(
                    wave, len(dead), len(ready) + len(pending)
                )
            )

            # 7. Prune all terminated threads from next iteration
            active_threads = ready + pending

        self.send_event.clear()
        self.read_event.clear()


    def process(self, work_queue, thread_count = 2, timeout = 10, send_delay = 0.10, **race_args):
        """Creates and drives a collection of :class:`~.Thread`\s through a list of work items.

        Parameters
        ------------
        work_queue : list
            A list of :class:`~requests.Request`\s or callables for the threads to process.
            If :obj:`work_queue` isn't a list, it will be converted to a single-item list.
            See :class:`~.Thread` documentation for additional details.
        thread_count : int, optional
            The number of threads to create.
            Default is ``2``.
        timeout : float, optional
            How long to wait, in seconds, before considering a :class:`~.Thread` to have timed out.
            Timed out :class:`~.Thread`\s may continue to run, but are no longer driven directly or waited on.
            Default is ``10`` seconds.
        send_delay : float, optional
            How long to wait after synchronizing before allowing :class:`~.BaseConnection`\s to finish sending data.
            Increasing this may improve timing precision by allowing sockets to fully flush.
            Increasing this value too much may result in socket timeouts.
            Default is ``0.10`` seconds.
        **race_args : dict
            Keyword arguments to pass to the :class:`~.Thread` and :class:`~.BaseConnection` constructors.

        Returns
        ---------
        list
            A list of :class:`~.Thread` objects used.
            Of particular interest are the :obj:`response` and :obj:`all_responses` attributes.
        """
        self.threads = self.create_threads(work_queue, thread_count, race_args)
        self.drive_threads(self.threads, timeout, send_delay)

        for i, thread in enumerate(self.threads):
            thread.join(timeout)
            if thread.is_alive():
                self.logger.warn("Thread {} failed to join".format(i))

        return self.threads