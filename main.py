import logging; logging.basicConfig(level=logging.INFO)
import newrelic.agent; newrelic.agent.initialize()

import random
import time

import gevent
from gevent import monkey; monkey.patch_all()

import os

from app.user_session import UserSession


SURVEY_RUNNER_URL = os.getenv('SURVEY_RUNNER_URL', 'http://localhost:5000')

NUM_WORKERS = int(os.getenv('NUM_WORKERS', '1'))
NUM_REQUESTS_PER_WORKER = os.getenv('NUM_REQUESTS_PER_WORKER', None)
if NUM_REQUESTS_PER_WORKER:
    NUM_REQUESTS_PER_WORKER = int(NUM_REQUESTS_PER_WORKER)

WAIT_BETWEEN_PAGES_MIN = int(os.getenv('WAIT_BETWEEN_PAGES_MIN', '5'))
WAIT_BETWEEN_PAGES_MAX = int(os.getenv('WAIT_BETWEEN_PAGES_MAX', '6'))

log = logging.getLogger(__name__)


def worker(num_requests):
    while num_requests is None or num_requests > 0:
        try:
            wait_between_pages = random.randrange(WAIT_BETWEEN_PAGES_MIN, WAIT_BETWEEN_PAGES_MAX)
            log.info('New user session, waiting %d seconds between pages', wait_between_pages)
            session = UserSession(SURVEY_RUNNER_URL, wait_between_pages)
            session.complete_survey('household', 'census')
            if num_requests is not None:
                num_requests -= 1
        except Exception:
            log.exception('Error running session, will retry in 30 seconds')
            time.sleep(30)


if __name__ == '__main__':

    log.info(
        'Running %d workers, each making %s requests',
        NUM_WORKERS,
        NUM_REQUESTS_PER_WORKER
    )

    workers = []
    for i in range(NUM_WORKERS):
        workers.append(gevent.spawn(worker, NUM_REQUESTS_PER_WORKER))
        time.sleep(1)
    gevent.joinall(workers)
