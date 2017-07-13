"""Demonstrates faking `Request`s for debugging purposes."""
import requests
import pyrace


def display_results(threads):
    for thread_num, thread in enumerate(threads):
        print("Thread {}:".format(thread_num))

        # Every `Response` has a `request` attribute with the `PreparedRequest` that was sent.
        # This is a mocked `Response` that only has a `request` attribute.
        prepared = thread.response.request
        print("  URL: {}".format(prepared.url))
        print("  X-Rand: {}".format(prepared.headers['X-Rand']))
        print("  Cookie: {}".format(prepared.headers['Cookie']))
        print("")


driver = pyrace.Driver()

# These will undergo statement evaluation, but are never sent.
# Attempting to actually send to this URL will result in an error.
url = 'https://request_never_sent/<<<["A","B"][self.thread_num%2]>>>'
headers = {'X-Rand': '<<<random.random()>>>'}
cookies = {'time': '<<<time.time()>>>'}
request = requests.Request('GET', url, headers = headers, cookies = cookies)
work_queue = [request]

threads = driver.process(work_queue, thread_count = 4, do_eval = True, fake_send = True)
display_results(threads)