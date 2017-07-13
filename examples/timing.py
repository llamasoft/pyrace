"""Interactive demonstration of the performance of the pyrace package."""
import argparse
import logging
import math
import pyrace
import requests
import textwrap


def setup_logging(verbosity):
    # Setting log level based on verbosity
    log_level = logging.WARNING
    if verbosity >= 2:
        log_level = logging.DEBUG
    elif verbosity >= 1:
        log_level = logging.INFO
    logging.basicConfig(level = log_level)


def display_timings(timings):
    print("{:16s} | {:10s} | {:10s}".format("Absolute Time", "vs Start", "vs Prev"))
    print("-" * 45)
    if not timings: return

    timings = sorted(timings)
    min_time = min(timings)
    prev_time = timings[0]
    for time in timings:
        relative_time = (time - min_time)
        step_time = (time - prev_time)
        prev_time = time
        print("{:16.5f} | +{:6.2f} ms | +{:6.2f} ms".format(time, 1000 * relative_time, 1000 * step_time))

    samples = len(timings)
    elapsed = (timings[-1] - timings[0])
    print("")
    print("Total Time:   {:.2f} ms".format(1000 * elapsed))
    print("Time/Request: {:.2f} ms".format(1000 * elapsed / samples))
    print("Request/Sec:  {:.0f}".format(samples / elapsed))


class CustomHelpTextFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, *args, **kwargs):
        super(CustomHelpTextFormatter, self).__init__(*args, **kwargs)
        self._max_help_position = min(self._max_help_position, 8)
        self._width = max(self._width, 100)

    def _split_lines(self, text, width):
        text = textwrap.dedent(text)
        text = text.strip("\r\n")
        text += "\n\n"
        return text.splitlines()


def get_args():
    parser = argparse.ArgumentParser(formatter_class = CustomHelpTextFormatter)
    parser.add_argument("thread_count",
        type=int,
        help="""
            Number of simultaneous request threads to run.
            Recommended values are between 2 and 10.
        """
    )
    parser.add_argument("-i", "--iterations",
        type=int,
        dest="iterations",
        default=1,
        help="""
            The number of test iterations to run.
            Default is %(default)s, recommended is between 1 and 10.
        """
    )
    parser.add_argument("-d", "--delay",
        type=float,
        dest="send_delay",
        default=0.10,
        help="""
            Number of seconds to delay before finalizing requests.
            On slower internet connections, increasing this value may improve performance.
            Increasing the value too much (beyond a few seconds) may cause timeouts.
            Default is %(default)s, recommended is between 0 and 2.
        """
    )
    parser.add_argument("-c", "--connect",
        type=str,
        dest="connect_mode",
        choices=['normal', 'same', 'diff', 'rand'],
        default="same",
        help="""
            How hostname-to-IP mapping is handled.
            Normal: each connection does their own DNS lookup.
            Same: all connections use the same host IP address.
            Diff: all connections use different host IP addresses.
            Rand: each connection selects a random host IP address.
            Enable INFO logging to see thread connection IP addresses.
            Default is '%(default)s'.
        """
    )
    parser.add_argument("-v", "--verbose",
        action="count",
        help="""
            Increases the verbosity of the output.
            Once for INFO logging; twice for DEBUG.
        """
    )
    return parser.parse_args()


args = get_args()
setup_logging(args.verbose)

print("Thread Count: {}".format(args.thread_count))
print("Iterations:   {}".format(args.iterations))
print("Send Delay:   {} sec".format(args.send_delay))
print("Connect Mode: {}".format(args.connect_mode))
print("")


# This is the `Request` we'll be sending.
# This example simply GETs the current time.
request = requests.Request('GET', 'https://now.httpbin.org')

# The work queue is a list of `Requests` or callables to execute.
# In this case, it's N copies of our `Request`.
work_queue = [request] * args.iterations

# Returns the Threads used to process the `work_queue`.
# We are usually interested in the `all_responses` or `response` attributes.
driver = pyrace.Driver()
results = driver.process(work_queue,
    thread_count = args.thread_count,
    send_delay   = args.send_delay,
    connect_mode = args.connect_mode
)


for i in xrange(args.iterations):
    print("{:=^60}".format(" Iteration {} ".format(i+1)))
    print("")

    # To get the Nth `Response` we use ``t.all_responses[N]``.
    # If we only wanted the most recent `Response`, ``t.response`` could be used instead.
    responses = [r.all_responses[i] for r in results]
    timings = [r.json()['now']['epoch'] for r in responses]

    display_timings(timings)
    print("")
