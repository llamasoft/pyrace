"""Demonstrates callback functionality by mocking CSRF token extraction."""
import requests
import pyrace
import binascii


def extract_token(self):
    # This function is given a `Thread`'s `self` as its only argument.

    # Here we pretend that the random bytes are a CSRF token.
    # We extract the token, then create a fake login `Request` using it.
    csrf_token = binascii.hexlify(self.response.content)
    request_data = {'user': 'pyrace', 'pass': 'root', 'token': csrf_token}
    login_request = requests.Request('POST', 'https://httpbin.org/post', data = request_data)

    # Adding the new `Request` to the `Thread`'s `work_queue`.
    self.work_queue.append(login_request)


def display_results(threads):
    for thread_num, thread in enumerate(threads):
        print("Thread {}: {}".format(thread_num, thread.response.json()['form']))


driver = pyrace.Driver()

# Fetch the token, then execute the callback to create a `Request` using it.
token_request = requests.Request('GET', 'https://httpbin.org/bytes/16')
work_queue = [token_request, extract_token]

result_threads = driver.process(work_queue, thread_count = 3)
display_results(result_threads)