import json
import logging;logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
import newrelic.agent; newrelic.agent.initialize()

import time

import gevent
from gevent import monkey; monkey.patch_all()

import os

import requests

from app.user_session import UserSession


SURVEY_RUNNER_URL = os.getenv('SURVEY_RUNNER_URL', 'http://localhost:5000')
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK')
SLACK_CHANNEL = os.getenv('SLACK_CHANNEL', '#catd')

NUM_WORKERS = int(os.getenv('NUM_WORKERS', '1'))
SUBMISSIONS = os.getenv('SUBMISSIONS', None)
if SUBMISSIONS:
    SUBMISSIONS = int(SUBMISSIONS)

WAIT_BETWEEN_PAGES = int(os.getenv('WAIT_BETWEEN_PAGES', '5'))
SURVEY_TIME_SUCCESS = int(os.getenv('SURVEY_TIME_SUCCESS', '15'))

log = logging.getLogger(__name__)


def worker(worker_id):
    results = []
    num_submissions = SUBMISSIONS
    while num_submissions is None or num_submissions > 0:
        try:
            start_time = time.time()
            log.info('[%d] Starting survey', worker_id)
            session = UserSession(SURVEY_RUNNER_URL, WAIT_BETWEEN_PAGES)
            session.start()
            survey_time = time.time() - start_time
            results.append(survey_time)
            log.info('[%d] Survey completed in %f seconds', worker_id, survey_time)
            if num_submissions is not None:
                num_submissions -= 1
        except Exception:
            log.exception('Error running session, will retry in 30 seconds')
            time.sleep(30)

    return results


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


if __name__ == '__main__':

    log.info(
        'Running %d workers each making %s submissions waiting %d seconds between pages',
        NUM_WORKERS,
        str(SUBMISSIONS) if SUBMISSIONS else 'unlimited',
        WAIT_BETWEEN_PAGES
    )

    workers = []
    for i in range(NUM_WORKERS):
        workers.append(gevent.spawn(worker, i))
        time.sleep(77 * WAIT_BETWEEN_PAGES / NUM_WORKERS)
    results = [r.value for r in gevent.joinall(workers)]
    results = [item for sublist in results for item in sublist]

    average_survey_time = sum(results)/len(results)
    log.info('Average survey completion time was %.2f seconds', average_survey_time)

    announce_results(
        'The average survey completion time was *{:.2f}* seconds\n_{} workers each making {} submissions waiting {} seconds between pages_'.format(
            average_survey_time,
            NUM_WORKERS,
            SUBMISSIONS if SUBMISSIONS else 'unlimited',
            WAIT_BETWEEN_PAGES
        ),
        "#D00000" if average_survey_time > SURVEY_TIME_SUCCESS else "00D000"
    )
