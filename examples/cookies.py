"""Demonstrates how outgoing cookies can be saved for future requests."""
import requests
import pyrace


def display_cookies(responses):
    print("Server Cookie: {}".format(responses[0].json()['cookies']))
    print("Manual Cookie: {}".format(responses[1].json()['cookies']))
    print("Result Cookie: {}".format(responses[2].json()['cookies']))
    print("")


driver = pyrace.Driver()

# The server will set a cookie called `server_set`.
server_cookie = requests.Request('GET', 'https://httpbin.org/cookies/set?server_set=this_cookie')

# Manually adds a `we_sent` cookie, then lists our `Session`'s cookies.
manual_cookie = requests.Request('GET', 'https://httpbin.org/cookies', cookies = {'we_sent': 'this_one'})

# Lists our `Session`'s cookies.
list_cookies = requests.Request('GET', 'https://httpbin.org/cookies')

# Have the server set a cookie, let us manually send one, then list the `Session`'s cookies.
work_queue = [server_cookie, manual_cookie, list_cookies]


# Save manually sent cookies for future `Requests`. (This is the default behavior.)
# At the end of this, the cookie that the server set exists, as does our manual cookie.
# See `Thread` documentation for details.
results = driver.process(work_queue, thread_count = 1, save_sent_cookies = True)
print("{:=^60}".format(" save_sent_cookies: True "))
display_cookies(results[0].all_responses)


# Discard manually sent cookies at the end of each `Request`.
# At the end of this, the cookie that the server set exists, but *not* our manual cookie.
results = driver.process(work_queue, thread_count = 1, save_sent_cookies = False)
print("{:=^60}".format(" save_sent_cookies: False "))
display_cookies(results[0].all_responses)
