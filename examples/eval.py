"""Demonstrates the evaluation of embedded statements within `Request`s."""
import requests
import pyrace


def display_results(threads):
    for thread_num, thread in enumerate(threads):
        print("Thread {}: {}".format(thread_num, thread.response.json()['form']))


driver = pyrace.Driver()
threads = 3

request_data = {'thread_num': '<<<self.thread_num>>>', 'rand': '<<<random.random()>>>'}
request = requests.Request('POST', 'https://httpbin.org/post', data = request_data)
work_queue = [request]


# Do not evaluate embedded statements in `Request`s.  (This is the default behavior.)
print("{:=^60}".format(" do_eval: False "))
result_threads = driver.process(work_queue, thread_count = threads, do_eval = False)
display_results(result_threads)
print("")


# Evaluate embedded statements in all `Request` fields.
# These statements are evaluated at the `Thread` level.
# Any value or module that the `Thread` has access to may be used.
# See `Thread` documentation for details.
print("{:=^60}".format(" do_eval: True "))
result_threads = driver.process(work_queue, thread_count = threads, do_eval = True)
display_results(result_threads)