import logging
import re
import time

import newrelic.agent

import requests

from app.token_generator import create_token

log = logging.getLogger(__name__)


class UserSession:

    def __init__(self, host, wait_between_pages):
        self._host = host
        self._wait_between_pages = wait_between_pages
        self._session = requests.session()
        self.page_load_times = []

    def wait_and_submit_answer(self, post_data=None, url=None, action='save_continue', action_value=''):
        time.sleep(self._wait_between_pages)
        self.submit_answer(post_data, url, action, action_value)

    @newrelic.agent.background_task()
    def submit_answer(self, post_data, url, action, action_value):
        start_time = time.time()
        url = self._host + url if url else self.last_url

        _post_data = (post_data.copy() or {}) if post_data else {}
        if self.last_csrf_token is None:
            raise Exception("Missing CSRF token")

        _post_data.update({'csrf_token': self.last_csrf_token})

        if action:
            _post_data.update({'action[{action}]'.format(action=action): action_value})

        headers = {
            'Referer': self.last_url,
            'X-Request-Start': str(int(time.time()*1000))
        }

        response = self._session.post(url, data=_post_data, headers=headers, allow_redirects=False)

        if response.status_code == 302:
            headers = {
                'Referer': response.headers['location'],
                'X-Request-Start': str(int(time.time()*1000))
            }

            response = self._session.get(response.headers['location'], headers=headers, allow_redirects=False)

        if response.status_code != 200:
            raise Exception('Got back a non-200: {}'.format(response.status_code))

        self._cache_response(response)
        self.page_load_times.append(time.time() - start_time)

    def _cache_response(self, response):
        self.last_csrf_token = self._extract_csrf_token(response.text)
        self.last_response = response
        self.last_url = response.url

    @staticmethod
    def _extract_csrf_token(html):
        match = re.search(r'<input id="csrf_token" name="csrf_token" type="hidden" value="(.+?)">', html)
        return (match.group(1) or None) if match else None

    def assert_in_page(self, content):
        if str(content) not in self.last_response.text:
            raise Exception('Expected content "{}" not in page {}, status code was {}'.format(
                content,
                self.last_url,
                self.last_response.status_code
            ))

    @newrelic.agent.background_task()
    def launch_survey(self, form_type_id, eq_id, **payload_kwargs):
        token = create_token(form_type_id=form_type_id, eq_id=eq_id, **payload_kwargs)
        url = '/session?token=' + token
        response = self._session.get(self._host + url, allow_redirects=False)

        if response.status_code != 302:
            raise Exception('Got a non-302 back when authenticating session: {}'.format(response.status_code))

        response = self._session.get(response.headers['location'])

        self._cache_response(response)

    def start(self):
        variant_flags = {'sexual_identity': 'false'}
        self.launch_survey('household', 'census', region_code='GB-ENG', variant_flags=variant_flags, roles=['dumper'])

        self.wait_and_submit_answer(action='start_questionnaire')

        self.complete_who_lives_here_section()  # 10 pages

        self.complete_household_and_accommodation_section()  # 10 pages

        self.complete_individual_section_person_1()  # 39 pages

        self.complete_individual_section_person_2()  # 7 pages

        self.complete_visitors_section_visitor_1()  # 6 pages

        self.complete_visitors_section_visitor_2()  # 7 pages

        self.complete_survey()

    @newrelic.agent.background_task()
    def complete_survey(self):
        self.assert_in_page('You’re ready to submit your 2017 Census Test')
        #
        # resp = self._session.get(self._host + '/dump/submission')
        # eg = {'submission': {'case_id': 'a360486f-c5c9-4e73-9da4-66c5e6a742fd', 'collection': {'exercise_sid': 'f1291d42-1141-4833-aa9b-b6514d9b0210', 'instrument_id': 'household', 'period': '201604'}, 'data': [{'answer_id': 'address-line-1', 'answer_instance': 0, 'group_instance': 0, 'value': '44 hill side'}, {'answer_id': 'address-line-2', 'answer_instance': 0, 'group_instance': 0, 'value': 'cimla'}, {'answer_id': 'address-line-3', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'town-city', 'answer_instance': 0, 'group_instance': 0, 'value': 'neath'}, {'answer_id': 'county', 'answer_instance': 0, 'group_instance': 0, 'value': 'west glamorgan'}, {'answer_id': 'postcode', 'answer_instance': 0, 'group_instance': 0, 'value': 'cf336gn'}, {'answer_id': 'country', 'answer_instance': 0, 'group_instance': 0, 'value': 'wales'}, {'answer_id': 'permanent-or-family-home-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'first-name', 'answer_instance': 0, 'group_instance': 0, 'value': 'Danny'}, {'answer_id': 'first-name', 'answer_instance': 1, 'group_instance': 0, 'value': 'Anjali'}, {'answer_id': 'middle-names', 'answer_instance': 0, 'group_instance': 0, 'value': 'K'}, {'answer_id': 'middle-names', 'answer_instance': 1, 'group_instance': 0, 'value': 'K'}, {'answer_id': 'last-name', 'answer_instance': 0, 'group_instance': 0, 'value': 'Boje'}, {'answer_id': 'last-name', 'answer_instance': 1, 'group_instance': 0, 'value': 'Yo'}, {'answer_id': 'everyone-at-address-confirmation-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'overnight-visitors-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 2}, {'answer_id': 'household-relationships-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Husband or wife'}, {'answer_id': 'type-of-accommodation-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Whole house or bungalow'}, {'answer_id': 'type-of-house-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Detached'}, {'answer_id': 'self-contained-accommodation-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'No'}, {'answer_id': 'number-of-bedrooms-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 2}, {'answer_id': 'central-heating-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['Gas', 'Electric (include storage heaters)', 'Oil', 'Solid fuel (for example wood, coal)', 'Renewable (for example solar panels)', 'Other central heating', 'No central heating']}, {'answer_id': 'own-or-rent-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Owns outright'}, {'answer_id': 'number-of-vehicles-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 2}, {'answer_id': 'details-correct-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes, this is my full name'}, {'answer_id': 'over-16-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'private-response-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'No, I do not want to request a personal form'}, {'answer_id': 'sex-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Male'}, {'answer_id': 'date-of-birth-answer', 'answer_instance': 0, 'group_instance': 0, 'value': '1988-05-12'}, {'answer_id': 'marital-status-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'In a registered same-sex civil partnership'}, {'answer_id': 'another-address-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes, an address within the UK'}, {'answer_id': 'another-address-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'other-address-answer-building', 'answer_instance': 0, 'group_instance': 0, 'value': '12'}, {'answer_id': 'other-address-answer-street', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'other-address-answer-city', 'answer_instance': 0, 'group_instance': 0, 'value': 'Newport'}, {'answer_id': 'other-address-answer-county', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'other-address-answer-postcode', 'answer_instance': 0, 'group_instance': 0, 'value': 'NP10 8XG'}, {'answer_id': 'address-type-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Other'}, {'answer_id': 'address-type-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': 'Friends Home'}, {'answer_id': 'in-education-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'term-time-location-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'country-of-birth-england-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'England'}, {'answer_id': 'country-of-birth-england-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'country-of-birth-wales-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'carer-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes, 1 -19 hours a week'}, {'answer_id': 'national-identity-england-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['English', 'Welsh', 'Scottish', 'Northern Irish', 'British', 'Other']}, {'answer_id': 'national-identity-england-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': 'Ind'}, {'answer_id': 'national-identity-wales-answer', 'answer_instance': 0, 'group_instance': 0, 'value': []}, {'answer_id': 'national-identity-wales-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'ethnic-group-england-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Other ethnic group'}, {'answer_id': 'other-ethnic-group-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Other'}, {'answer_id': 'other-ethnic-group-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': 'Telugu'}, {'answer_id': 'language-england-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'English'}, {'answer_id': 'language-england-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'language-welsh-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'religion-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['No religion', 'Buddhism', 'Hinduism', 'Judaism', 'Islam', 'Sikhism', 'Other']}, {'answer_id': 'religion-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': 'Ind'}, {'answer_id': 'past-usual-address-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'This address'}, {'answer_id': 'past-usual-address-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'passports-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['United Kingdom']}, {'answer_id': 'disability-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes, limited a lot'}, {'answer_id': 'qualifications-england-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['Masters Degree', 'Postgraduate Certificate / Diploma']}, {'answer_id': 'qualifications-welsh-answer', 'answer_instance': 0, 'group_instance': 0, 'value': []}, {'answer_id': 'employment-type-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['none of the above']}, {'answer_id': 'jobseeker-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'job-availability-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'job-pending-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'occupation-answer', 'answer_instance': 0, 'group_instance': 0, 'value': ['a student', 'long-term sick or disabled']}, {'answer_id': 'ever-worked-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes'}, {'answer_id': 'main-job-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'an employee'}, {'answer_id': 'hours-worked-answer', 'answer_instance': 0, 'group_instance': 0, 'value': '31 - 48'}, {'answer_id': 'work-travel-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Train'}, {'answer_id': 'job-title-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Software Engineer'}, {'answer_id': 'job-description-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Development'}, {'answer_id': 'main-job-type-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Employed by an organisation or business'}, {'answer_id': 'business-name-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'ONS'}, {'answer_id': 'employers-business-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Civil Servant'}, {'answer_id': 'details-correct-answer', 'answer_instance': 0, 'group_instance': 1, 'value': 'Yes, this is my full name'}, {'answer_id': 'over-16-answer', 'answer_instance': 0, 'group_instance': 1, 'value': 'Yes'}, {'answer_id': 'private-response-answer', 'answer_instance': 0, 'group_instance': 1, 'value': 'Yes, I want to request a personal form'}, {'answer_id': 'visitor-first-name', 'answer_instance': 0, 'group_instance': 0, 'value': 'Diya'}, {'answer_id': 'visitor-last-name', 'answer_instance': 0, 'group_instance': 0, 'value': 'K'}, {'answer_id': 'visitor-sex-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Female'}, {'answer_id': 'visitor-date-of-birth-answer', 'answer_instance': 0, 'group_instance': 0, 'value': '2016-11-04'}, {'answer_id': 'visitor-uk-resident-answer', 'answer_instance': 0, 'group_instance': 0, 'value': 'Yes, usually lives in the United Kingdom'}, {'answer_id': 'visitor-uk-resident-answer-other', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'visitor-address-answer-building', 'answer_instance': 0, 'group_instance': 0, 'value': '309'}, {'answer_id': 'visitor-address-answer-street', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'visitor-address-answer-city', 'answer_instance': 0, 'group_instance': 0, 'value': 'Vizag'}, {'answer_id': 'visitor-address-answer-county', 'answer_instance': 0, 'group_instance': 0, 'value': ''}, {'answer_id': 'visitor-address-answer-postcode', 'answer_instance': 0, 'group_instance': 0, 'value': '530003'}, {'answer_id': 'visitor-first-name', 'answer_instance': 0, 'group_instance': 1, 'value': 'Niki'}, {'answer_id': 'visitor-last-name', 'answer_instance': 0, 'group_instance': 1, 'value': 'K'}, {'answer_id': 'visitor-sex-answer', 'answer_instance': 0, 'group_instance': 1, 'value': 'Male'}, {'answer_id': 'visitor-date-of-birth-answer', 'answer_instance': 0, 'group_instance': 1, 'value': '1985-10-17'}, {'answer_id': 'visitor-uk-resident-answer', 'answer_instance': 0, 'group_instance': 1, 'value': 'Yes, usually lives in the United Kingdom'}, {'answer_id': 'visitor-uk-resident-answer-other', 'answer_instance': 0, 'group_instance': 1, 'value': ''}, {'answer_id': 'visitor-address-answer-building', 'answer_instance': 0, 'group_instance': 1, 'value': '1009'}, {'answer_id': 'visitor-address-answer-street', 'answer_instance': 0, 'group_instance': 1, 'value': ''}, {'answer_id': 'visitor-address-answer-city', 'answer_instance': 0, 'group_instance': 1, 'value': 'Detroit'}, {'answer_id': 'visitor-address-answer-county', 'answer_instance': 0, 'group_instance': 1, 'value': ''}, {'answer_id': 'visitor-address-answer-postcode', 'answer_instance': 0, 'group_instance': 1, 'value': '12345'}], 'flushed': False, 'metadata': {'ref_period_end_date': '2016-04-30', 'ref_period_start_date': '2016-04-01', 'ru_ref': '123456789012A', 'user_id': 'integration-test'}, 'origin': 'uk.gov.ons.edc.eq', 'started_at': '2018-10-31T11:44:13.151978+00:00', 'submitted_at': '2018-10-31T11:44:23.085403+00:00', 'survey_id': 'census', 'tx_id': '8330ac0c-ecbb-4f01-8877-b6eac5d0a412', 'type': 'uk.gov.ons.edc.eq:surveyresponse', 'version': '0.0.2'}}
        #
        # expected_flat = {str(a['group_instance']) + '-' + str(a['answer_instance']) + '-' + a['answer_id']: a['value'] for a in eg['submission']['data']}
        # #actual_flat = {str(a['group_instance']) + '-' + str(a['answer_instance']) + '-' + a['answer_id']: a['value'] for a in resp.json()['submission']['data']}
        # actual_flat = {str(a['GroupInstance']) + '-' + str(a['AnswerInstance']) + '-' + a['AnswerId']: a['Value'] for a in resp.json()}
        #
        # extra_keys = actual_flat.keys() - expected_flat.keys()
        # if extra_keys:
        #     raise Exception('Submission contained unexpected keys: {}'.format(extra_keys))
        #
        # for k, v in expected_flat.items():
        #     if not v:
        #         continue
        #
        #     if isinstance(v, int):
        #         v = str(v)
        #
        #     if isinstance(v, list):
        #         v = ','.join(v)
        #
        #     if k not in actual_flat:
        #         raise Exception('Submission missing value for {}'.format(k))
        #
        #     if actual_flat[k] != v:
        #         raise Exception('Submission contained unexpected value for {}, expected {} actual {}'.format(k, v, actual_flat[k]))

        self.wait_and_submit_answer()

        self.assert_in_page('Submission successful')

    def complete_visitors_section_visitor_1(self):
        post_data = [
            {
                'visitor-first-name': 'Diya',
                'visitor-last-name': 'K'
            },
            {
                'visitor-sex-answer': ['Female']
            },
            {
                'visitor-date-of-birth-answer-day': '4',
                'visitor-date-of-birth-answer-month': '11',
                'visitor-date-of-birth-answer-year': '2016',
            },
            {
                'visitor-uk-resident-answer': ['Yes, usually lives in the United Kingdom']
            },
            {
                'visitor-address-answer-building': '309',
                'visitor-address-answer-city': 'Vizag',
                'visitor-address-answer-postcode': '530003'
            },
        ]

        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('You have completed all questions for Visitor 1')
        self.wait_and_submit_answer(action='save_continue')

    def complete_visitors_section_visitor_2(self):
        post_data = [
            {
                'visitor-first-name': 'Niki',
                'visitor-last-name': 'K'
            },
            {
                'visitor-sex-answer': ['Male']
            },
            {
                'visitor-date-of-birth-answer-day': '17',
                'visitor-date-of-birth-answer-month': '10',
                'visitor-date-of-birth-answer-year': '1985',
            },
            {
                'visitor-uk-resident-answer': ['Yes, usually lives in the United Kingdom']
            },
            {
                'visitor-address-answer-building': '1009',
                'visitor-address-answer-city': 'Detroit',
                'visitor-address-answer-postcode': '12345'
            },
        ]
        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('You have completed all questions for Visitor 2')
        self.wait_and_submit_answer(action='save_continue')
        self.assert_in_page('You have successfully completed the ‘Visitors’ section')
        self.wait_and_submit_answer(action='save_continue')

    def complete_individual_section_person_1(self):
        post_data = [
            {
                'details-correct-answer': ['Yes, this is my full name']
            },
            {
                'over-16-answer': ['Yes']
            },
            {
                'private-response-answer': ['No, I do not want to request a personal form']
            },
            {
                'sex-answer': ['Male']
            },
            {
                'date-of-birth-answer-day': '12',
                'date-of-birth-answer-month': '5',
                'date-of-birth-answer-year': '1988',
            },
            {
                'marital-status-answer': ['In a registered same-sex civil partnership']
            },
            {
                'another-address-answer': ['Yes, an address within the UK']
            },
            {
                'other-address-answer-building': '12',
                'other-address-answer-city': 'Newport',
                'other-address-answer-postcode': 'NP10 8XG'
            },
            {
                'address-type-answer': ['Other'],
                'address-type-answer-other': 'Friends Home'
            },
            {
                'in-education-answer': ['Yes']
            },
            {
                'term-time-location-answer': ['Yes']
            },
            {
                'country-of-birth-england-answer': ['England']
            },
            {
                'carer-answer': ['Yes, 1 -19 hours a week']
            },
            {
                'national-identity-england-answer': ['English',
                                                     'Welsh',
                                                     'Scottish',
                                                     'Northern Irish',
                                                     'British',
                                                     'Other'],
                'national-identity-england-answer-other': 'Ind'
            },
            {
                'ethnic-group-england-answer': ['Other ethnic group']
            },
            {
                'other-ethnic-group-answer': ['Other'],
                'other-ethnic-group-answer-other': 'Telugu'
            },
            {
                'language-england-answer': ['English']
            },
            {
                'religion-answer': ['No religion',
                                    'Buddhism',
                                    'Hinduism',
                                    'Judaism',
                                    'Islam',
                                    'Sikhism',
                                    'Other'],
                'religion-answer-other': 'Ind'
            },
            {
                'past-usual-address-answer': ['This address']
            },
            {
                'passports-answer': ['United Kingdom']
            },
            {
                'disability-answer': ['Yes, limited a lot']
            },
            {
                'qualifications-england-answer': ['Masters Degree',
                                                  'Postgraduate Certificate / Diploma']
            },
            {
                'employment-type-answer': ['none of the above']
            },
            {
                'jobseeker-answer': ['Yes']
            },
            {
                'job-availability-answer': ['Yes']
            },
            {
                'job-pending-answer': ['Yes']
            },
            {
                'occupation-answer': ['a student',
                                      'long-term sick or disabled']
            },
            {
                'ever-worked-answer': ['Yes']
            },
            {
                'main-job-answer': ['an employee']
            },
            {
                'hours-worked-answer': ['31 - 48']
            },
            {
                'work-travel-answer': ['Train']
            },
            {
                'job-title-answer': 'Software Engineer'
            },
            {
                'job-description-answer': 'Development'
            },
            {
                'main-job-type-answer': ['Employed by an organisation or business']
            },
            {
                'business-name-answer': 'ONS'
            },
            {
                'employers-business-answer': 'Civil Servant'
            }
        ]
        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('There are no more questions for Danny Boje')
        self.wait_and_submit_answer(action='save_continue')
        self.assert_in_page('Anjali Yo')
        self.wait_and_submit_answer(action='save_continue')

    def complete_individual_section_person_2(self):
        post_data = [
            {
                'details-correct-answer': ['Yes, this is my full name']
            },
            {
                'over-16-answer': ['Yes']
            },
            {
                'private-response-answer': ['Yes, I want to request a personal form']
            }
        ]
        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('Request for personal and confidential form')
        self.wait_and_submit_answer(action='save_continue')

        self.assert_in_page('There are no more questions for Anjali Yo')
        self.wait_and_submit_answer(action='save_continue')
        self.assert_in_page('Name of visitor')
        self.wait_and_submit_answer(action='save_continue')

    def complete_household_and_accommodation_section(self):
        self.wait_and_submit_answer(action='save_continue')
        post_data = [
            {
                'type-of-accommodation-answer': ['Whole house or bungalow']
            },
            {
                'type-of-house-answer': ['Detached']
            },
            {
                'self-contained-accommodation-answer': ['No']
            },
            {
                'number-of-bedrooms-answer': '2'
            },
            {
                'central-heating-answer': [
                    'Gas',
                    'Electric (include storage heaters)',
                    'Oil',
                    'Solid fuel (for example wood, coal)',
                    'Renewable (for example solar panels)',
                    'Other central heating',
                    'No central heating'
                ]
            },
            {
                'own-or-rent-answer': ['Owns outright']
            },
            {
                'number-of-vehicles-answer': '2'
            },
        ]
        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('You have successfully completed the ‘Household and Accommodation’ section')
        self.wait_and_submit_answer(action='save_continue')
        self.assert_in_page('Danny Boje')
        self.wait_and_submit_answer(action='save_continue')

    def complete_who_lives_here_section(self):
        self.assert_in_page('What is your address?')
        self.assert_in_page('Who lives here?')
        self.assert_in_page('>Save and continue<')

        post_data = [
            {
                'address-line-1': '44 hill side',
                'address-line-2': 'cimla',
                'county': 'west glamorgan',
                'country': 'wales',
                'postcode': 'cf336gn',
                'town-city': 'neath'
            }
        ]

        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.wait_and_submit_answer(action='save_continue')

        post_data = [
            {
                'permanent-or-family-home-answer': ['Yes']
            },
            {
                # Person 1
                'household-0-first-name': 'Danny',
                'household-0-middle-names': 'K',
                'household-0-last-name': 'Boje',
                # Person 2
                'household-1-first-name': 'Anjali',
                'household-1-middle-names': 'K',
                'household-1-last-name': 'Yo'
            },
            {
                'everyone-at-address-confirmation-answer': ['Yes']
            },
            {
                'overnight-visitors-answer': '2'
            },
            {
                'household-relationships-answer-0': 'Husband or wife'
            }
        ]
        for post in post_data:
            self.wait_and_submit_answer(post_data=post)

        self.assert_in_page('You have successfully completed the ‘Who lives here?’ section')
        self.wait_and_submit_answer(action='save_continue')
