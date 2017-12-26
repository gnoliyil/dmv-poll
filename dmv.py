# -*- coding: utf-8 -*-
from selenium.webdriver import PhantomJS, Firefox
import requests
from bs4 import BeautifulSoup
import jsondate as json
import time
import datetime
import exceptions
import logging
import traceback
from itertools import product
from threading import Timer
from dateutil import parser
from push_message import PushMessage


def remap_keys(dic):
    return {str(key): value for key, value in dic.iteritems()}


def unmap_keys(dic):
    return {parser.parse(key): value for key, value in dic.iteritems()}


class DMVPoll:
    CONFIG_FILE = "./config.json"
    SENT_LOG = "./sent.json"
    DMV_HOMEPAGE = "https://dmv.ca.gov/"
    DMV_QUERY_URL = "https://www.dmv.ca.gov/wasapp/foa/findDriveTest.do"
    TIMEOUT = 10
    DMV_DATEFORMAT = "%a, %d %b %Y"
    DMV_TIMEFORMAT = "%H%M"

    def __init__(self):
        self.push = PushMessage()
        self.config = json.load(open(self.CONFIG_FILE, "r"))
        self.browser = Firefox()
        self.session = requests.Session()
        self.cookies = self.session.cookies
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.11; '
                                                   'rv:57.0) Gecko/20100101 Firefox/57.0'})
        self.earliest_date = None
        try:
            self.sent = unmap_keys(json.load(open(self.SENT_LOG, "r")))
            print self.sent
        except Exception:
            self.sent = {}

    def get_cookie(self):
        self.cookies.clear()
        self.browser.delete_all_cookies()
        self.browser.get(self.DMV_HOMEPAGE)
        timeout = time.time() + self.TIMEOUT
        while len(self.browser.get_cookies()) < 2:
            if time.time() > timeout:
                raise exceptions.RuntimeError("Timeout when get cookies from the browser")

        cookies_dict = self.browser.get_cookies()
        for cookie in cookies_dict:
            self.cookies.set(cookie["name"], cookie["value"],
                             path=cookie["path"], domain=cookie["domain"],
                             expires=cookie["expiry"], secure=cookie["secure"])

    def get_homepage(self):
        print self.cookies.items()
        response = self.session.get("http://www.dmv.ca.gov/portal/dmv",
                                    allow_redirects=True, cookies=self.cookies)
        print response.status_code
        print response.content

    def query_available_time(self, date):
        if self.earliest_date is None:
            self.get_earliest_date()
        earliest_date = self.earliest_date

        if earliest_date - date > datetime.timedelta(0):
            return {
                'result': 'error',
                'earliest': earliest_date
            }
        else:
            date_str = date.strftime(self.DMV_DATEFORMAT)
            time_str = date.strftime(self.DMV_TIMEFORMAT)
            response = self.session.post(self.DMV_QUERY_URL, data={
                'formattedRequestedDate': date_str,
                'requestedTime': time_str,
                'checkAvail': 'Check for Availablity'
            })
            soup = BeautifulSoup(response.content, "lxml")
            appointment = map(lambda x: x.get_text().strip(), soup.select('[data-title=Appointment] p'))
            if len(appointment) < 2:
                return {
                    'result': 'error',
                    'error': 'date/time not found'
                }
            available_time = parser.parse(appointment[1])
            if abs(available_time - date) > datetime.timedelta(minutes=20):
                return {
                    'result': 'error',
                    'earliest': available_time
                }
            else:
                return {
                    'result': 'success',
                    'time': available_time
                }

    def clear_earliest_date(self):
        self.earliest_date = None

    def get_earliest_date(self):
        firstname, lastname = self.config["dmv"]["name"].split(' ')
        dob_m, dob_d, dob_y = self.config["dmv"]["dob"].split('/')
        tel_1, tel_2, tel_3 = self.config["dmv"]["phone"].split('-')
        license_number = self.config["dmv"]["id"]
        office_id = self.config["dmv"]["office"]
        # query first available time
        response = self.session.post(self.DMV_QUERY_URL, data={
            'numberItems': 1,
            'mode': 'DriveTest',
            'officeId': office_id,
            'requestedTask': 'DT',
            'firstName': firstname,
            'lastName': lastname,
            'dlNumber': license_number,
            'birthMonth': dob_m,
            'birthDay': dob_d,
            'birthYear': dob_y,
            'telArea': tel_1,
            'telPrefix': tel_2,
            'telSuffix': tel_3,
            'resetCheckFields': 'true'
        })
        soup = BeautifulSoup(response.content, "lxml")
        appointment = map(lambda x: x.get_text().strip(), soup.select('[data-title=Appointment] p'))
        logging.info('Earliest ppointment = %s', appointment)
        self.earliest_date = parser.parse(appointment[1])
        return self.earliest_date

    def query_and_send(self, date):
        response = self.query_available_time(date)
        if response["result"] == 'success':
            new_date = response["time"]
            if new_date in self.sent and \
                    abs(datetime.datetime.now() - self.sent[new_date]) < datetime.timedelta(hours=1):
                return {
                    'result': 'error', 'error': 'time [{0}] already sent'.format(new_date)
                }
            else:
                self.sent[new_date] = datetime.datetime.now()
                return self.push.push('Time [{0}] is Available'.format(new_date), title='DMV Driving Test Appointment')
        else:
            return response

    def __del__(self):
        pass
        self.browser.close()

if __name__ == "__main__":
    logging.basicConfig(filename='dmv.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('DMVLogger')
    dmv = DMVPoll()

    def get_cookie():
        try:
            dmv.get_cookie()
            logger.info('Get cookie from browser, Cookies: %s', dmv.cookies.items())
        except Exception as e:
            logger.error(e.message)

        Timer(60, get_cookie, ()).start()

    def get_availble_times():
        try:
            dmv.get_earliest_date()
            for date_str, time_str in product(reversed(dmv.config["dmv"]["date"]), reversed(dmv.config["dmv"]["time"])):
                    datetime_str = date_str + ' ' + time_str
                    dt = parser.parse(datetime_str)
                    r = dmv.query_and_send(dt)
                    logger.info('Query time [%s], Result: %s', dt, r)
                    if r['result'] == 'error' and r['earliest'] - dt > datetime.timedelta(hours=2):
                        break
        except Exception as e:
            traceback.print_exc()
            logger.error(e.message)
        Timer(10, get_availble_times, ()).start()

    def save_sent_log():
        try:
            json.dump(remap_keys(dmv.sent), open(dmv.SENT_LOG, 'w'))
        except Exception as e:
            logger.error(e.message)
        Timer(60, save_sent_log, ()).start()

    get_cookie()
    get_availble_times()
    save_sent_log()
