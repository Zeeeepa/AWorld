import random
import time
import os

os.environ["MONITOR_SERVICE_NAME"] = "otlp_example"
os.environ["LOGFIRE_WRITE_TOKEN"] = ""

from aworld.metrics.metric import MetricType
from aworld.metrics.context_manager import MetricContext, ApiMetricTracker
from aworld.metrics.template import MetricTemplate



my_counter = MetricTemplate(
    type=MetricType.COUNTER,
    name="my_counter",
    description="My custom counter",
    unit="1"
)

my_gauge = MetricTemplate(
    type=MetricType.GAUGE,
    name="my_gauge"
)

my_histogram = MetricTemplate(
    type=MetricType.HISTOGRAM,
    name="my_histogram",
    buckets=[2,4,6,8,10]
)

@ApiMetricTracker()
def api():
    time.sleep(random.uniform(0, 1))

def custom_code():
    with ApiMetricTracker("test_custom_code"):
        time.sleep(random.uniform(0, 1))


if __name__ == '__main__':
    while 1:
        MetricContext.count(my_counter, random.randint(1, 10))
        MetricContext.gauge_set(my_gauge, random.randint(1, 10))
        MetricContext.histogram_record(my_histogram, random.randint(0, 1000))
        api()
        custom_code()
        time.sleep(random.random())
