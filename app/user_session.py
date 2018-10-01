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

    def wait_and_submit_answer(self, post_data=None, url=None, action='save_continue', action_value=''):
        time.sleep(self._wait_between_pages)
        self.submit_answer(post_data, url, action, action_value)

    @newrelic.agent.background_task()
    def submit_answer(self, post_data, url, action, action_value):
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

    def start(self, eq_id, form_type_id):
        variant_flags = {'sexual_identity': 'false'}
        self.launch_survey(eq_id, form_type_id, region_code='GB-ENG', variant_flags=variant_flags, roles=['dumper'])

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
        self.wait_and_submit_answer(action='save_continue')
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
        self.wait_and_submit_answer(action='save_continue')
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

        self.wait_and_submit_answer(post_data={'permanent-or-family-home-answer': ['Yes']})
        self.wait_and_submit_answer(action='add_answer')
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
