import requests
import pyrace

# The `Driver` class creates `Thread`s, provides them with a `work_queue`,
# and drives them through their `work_queue`s in a synchronized manner.
driver = pyrace.Driver()

# The `work_queue` list represents the work that each `Thread` should execute.
# The elements of a `work_queue` can be `Request`s or callable functions.
request = requests.Request('GET', 'https://now.httpbin.org')
work_queue = [request]

# The `process` method creates the specified number of worker `Thread`s,
# provides them each with a copy of the `work_queue`, then drives them
# through the `work_queue` tasks in a synchronized manner.
# The method returns a list of the `Thread` instances used.
result_threads = driver.process(work_queue, thread_count = 3)

# The primary `Thread` attributes we are interested in are `response` and `all_responses`.
# The `response` attribute contains the most recently returned `Response`.
# The `all_responses` attribute is a list of all `Response`s, in order.
# For information on `Response` objects, see Requests documentation:
#   http://docs.python-requests.org/en/master/user/quickstart/#response-content
for thread in result_threads:
    json_response = thread.response.json()
    epoch_time = json_response['now']['epoch']
    print("{:.4f}".format(epoch_time))
