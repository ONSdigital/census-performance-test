import json
import logging;logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

import time

import gevent
from gevent import monkey; monkey.patch_all()

import grpc.experimental.gevent as grpc_gevent; grpc_gevent.init_gevent()

from google.cloud import monitoring_v3

import os

import requests

from app.user_session import UserSession


SURVEY_RUNNER_URL = os.getenv('SURVEY_RUNNER_URL', 'http://localhost:5000')
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#catd')

STACKDRIVER_ENABLED = os.getenv('STACKDRIVER_ENABLED', 'false').lower() == 'true'

STACKDRIVER_BUCKETS = 40
STACKDRIVER_SCALE = 1
STACKDRIVER_GROWTH_FACTOR = 1.4

NUM_WORKERS = int(os.getenv('NUM_WORKERS', '1'))

MODE_CONTINUOUS = 'continuous'
MODE_AFTER_DEPLOY = 'after_deploy'
MODE_ONE_OFF = 'one_off'
MODE = os.getenv('MODE', MODE_CONTINUOUS)

SUBMISSIONS = int(os.getenv('SUBMISSIONS', '1'))

WAIT_BETWEEN_PAGES = int(os.getenv('WAIT_BETWEEN_PAGES', '5'))
PAGE_LOAD_TIME_SUCCESS = float(os.getenv('PAGE_LOAD_TIME_SUCCESS', '1.2'))

log = logging.getLogger(__name__)


def worker(worker_id):
    page_load_times = []
    num_submissions = SUBMISSIONS if MODE != MODE_CONTINUOUS else 1
    while num_submissions > 0:
        try:
            start_time = time.time()
            log.info('[%d] Starting survey', worker_id)
            session = UserSession(SURVEY_RUNNER_URL, WAIT_BETWEEN_PAGES)
            session.start()
            emit_stackdriver(session.page_load_times)
            page_load_times += session.page_load_times
            average_page_load_time = sum(session.page_load_times) / len(session.page_load_times)
            log.info('[%d] Survey completed in %f seconds, average page load time was %.2f seconds', worker_id, time.time() - start_time, average_page_load_time)
            if MODE != MODE_CONTINUOUS:
                num_submissions -= 1
        except Exception:
            log.exception('Error running session, will retry in 30 seconds')
            time.sleep(30)

    return page_load_times


def emit_stackdriver(page_load_times):
    if not STACKDRIVER_ENABLED:
        return

    instance_id = requests.get("http://metadata.google.internal./computeMetadata/v1/instance/id", headers={'Metadata-Flavor': 'Google'}).text
    zone = requests.get("http://metadata.google.internal./computeMetadata/v1/instance/zone", headers={'Metadata-Flavor': 'Google'}).text

    client = monitoring_v3.MetricServiceClient()
    project = os.environ['STACKDRIVER_PROJECT_ID']

    series = monitoring_v3.types.TimeSeries()
    series.metric.type = 'custom.googleapis.com/eq_perftest/page_load_time'
    # series.metric.labels
    series.resource.type = 'gke_container'
    series.resource.labels['project_id'] = project
    series.resource.labels['cluster_name'] = os.environ['STACKDRIVER_CLUSTER_NAME']
    series.resource.labels['container_name'] = os.environ['STACKDRIVER_CONTAINER_NAME']
    series.resource.labels['instance_id'] = instance_id
    series.resource.labels['namespace_id'] = os.environ['STACKDRIVER_NAMESPACE_UID']
    series.resource.labels['pod_id'] = os.environ['STACKDRIVER_POD_UID']
    series.resource.labels['zone'] = zone
    point = series.points.add()

    point.value.distribution_value.count = len(page_load_times)
    mean = sum(page_load_times) / len(page_load_times)
    point.value.distribution_value.mean = mean
    point.value.distribution_value.sum_of_squared_deviation = sum([(t - mean) ** 2 for t in page_load_times])

    point.value.distribution_value.bucket_options.exponential_buckets.num_finite_buckets = STACKDRIVER_BUCKETS
    point.value.distribution_value.bucket_options.exponential_buckets.growth_factor = STACKDRIVER_GROWTH_FACTOR
    point.value.distribution_value.bucket_options.exponential_buckets.scale = STACKDRIVER_SCALE

    counts = [0] * STACKDRIVER_BUCKETS
    for p in page_load_times:
        counts[get_stackdriver_bucket(p * 1000)] += 1
    point.value.distribution_value.bucket_counts.extend(counts)

    now = time.time()
    point.interval.end_time.seconds = int(now)
    point.interval.end_time.nanos = int((now - point.interval.end_time.seconds) * 10 ** 9)
    client.create_time_series(client.project_path(project), [series])


def get_stackdriver_bucket(page_load_time):
    for i in range(STACKDRIVER_BUCKETS - 1):
        if page_load_time < STACKDRIVER_SCALE * STACKDRIVER_GROWTH_FACTOR ** i:
            return i

    return STACKDRIVER_BUCKETS - 1


def get_version():
    try:
        return requests.get(SURVEY_RUNNER_URL + '/status').json()['version']
    except Exception:
        log.exception('Error getting version')
        return None


def announce_results(message, color):
    if not SLACK_WEBHOOK:
        return

    data = json.dumps({
        'channel': SLACK_CHANNEL,
        'attachments': [
            {
                "fallback": message,
                "color": color,
                "fields": [
                    {
                        "title": "Survey Runner Performance Test",
                        "value": message,
                        "short": False
                    }
                ]
            }
        ]
    })

    resp = requests.post(SLACK_WEBHOOK, data)
    log.info('Called slack webhook, response code %d', resp.status_code)


def run_workers():
    log.info(
        'Running %d workers each making %s submissions waiting %d seconds between pages',
        NUM_WORKERS,
        str(SUBMISSIONS) if MODE != MODE_CONTINUOUS else 'unlimited',
        WAIT_BETWEEN_PAGES
    )

    workers = []
    for i in range(NUM_WORKERS):
        workers.append(gevent.spawn(worker, i))
        time.sleep(77 * WAIT_BETWEEN_PAGES / NUM_WORKERS)
    page_load_times = [r.value for r in gevent.joinall(workers)]
    page_load_times = [item for sublist in page_load_times for item in sublist]

    average_page_load_time = sum(page_load_times) / len(page_load_times)
    log.info('Average page load time was %.2f seconds', average_page_load_time)

    announce_results(
        'The average page load time was *{:.2f}* seconds\n_{} workers each making {} submissions waiting {} seconds between pages_'.format(
            average_page_load_time,
            NUM_WORKERS,
            SUBMISSIONS,
            WAIT_BETWEEN_PAGES
        ),
        "#D00000" if average_page_load_time > PAGE_LOAD_TIME_SUCCESS else "00D000"
    )


if __name__ == '__main__':

    if MODE == MODE_AFTER_DEPLOY:
        tested_version = current_version = get_version()

        while True:
            while current_version is None or current_version == tested_version:
                log.info('Version has not changed from %s, waiting', tested_version)
                time.sleep(30)
                current_version = get_version()

            log.info('Version has changed from %s to %s, repeating tests', tested_version, current_version)

            run_workers()

            tested_version = current_version

    run_workers()
