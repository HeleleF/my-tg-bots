#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import requests
import logging
from threading import Thread
import time
import re

from secrets import DOMAIN, API_ENDPOINT

log = logging.getLogger('ored-tg')

class OredScraper:

    def __init__(self, on_data=None, on_error=None, delay: int=5):
        self.__running = False
        self.__sess = requests.Session()
        self.__sess.headers.update({
            'User-Agent': 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
        })
        self.__delay = delay
        self.__hds = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': DOMAIN,
            'Referer': f'{DOMAIN}/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        self.__payload = {
                "login": "false",
                "expireTimestamp": "0",
                "pokemon": "true",
                "lastpokemon": "true",
                "pokestops": "false",
                "lures": "false",
                "quests": "false",
                "dustamount": "0",
                "reloaddustamount": "false",
                "nests": "false",
                "invasions": "true",
                "lastnests": "false",
                "communities": "false",
                "lastcommunities": "false",
                "portals": "false",
                "pois": "false",
                "lastpois": "false",
                "newportals": "1",
                "lastportals": "false",
                "lastpokestops": "false",
                "gyms": "false",
                "lastgyms": "false",
                "badges": "false",
                "exEligible": "false",
                "lastslocs": "false",
                "spawnpoints": "false",
                "scanlocations": "false",
                "lastspawns": "false",
                "minIV": "97",
                "prevMinIV": "97",
                "minLevel": "NaN",
                "prevMinLevel": "0",
                "minPVP": "",
                "prevMinPVP": "0",
                "bigKarp": "false",
                "tinyRat": "false",
                "swLat": "52.623190318134554",
                "swLng": "13.151621818542482",
                "neLat": "52.65587329539442",
                "neLng": "13.261485099792482",
                "oSwLat": "52.623190318134554",
                "oSwLng": "13.151621818542482",
                "oNeLat": "52.65587329539442",
                "oNeLng": "13.261485099792482",
                "reids": "",
                "eids": "0",
		"exMinIV": "113,149"
        }
        
        self.__scraper_thread = None
        self.__remover_thread = None

        self.__action_cb = on_data
        self.__error_cb = on_error

        self.__filters = None

        self.__setup()

    def __setup(self) -> None:
        """ Calls the site once to get the token and setup the cookies """

        r = self.__sess.get(f'{DOMAIN}/')
        m = re.search(r'var token = \'(\S{42,48})\';', r.text)

        if m:
            log.debug(f'Token set to {m[1]}')
            self.__payload['token'] = m[1]
        else:

            log.error(f'No token found!')

            if self.__error_cb:
                self.__error_cb('No token found!')

    def __apply_filter(self, data):

        return data

    def __get_data(self):
        """ Queries data from the endpoint and returns it as a list"""

        try:
            response = self.__sess.post(f'{DOMAIN}/{API_ENDPOINT}', data=self.__payload, headers=self.__hds, timeout=10)
            response.raise_for_status()

        except requests.HTTPError as httpe:
            log.error(f'Get seasons failed with http error: {httpe}')
            if self.__error_cb:
                self.__error_cb(httpe)
            return []
        except requests.exceptions.ConnectionError as cerr:
            log.error(f'Get seasons failed with network problems: {cerr}')
            if self.__error_cb:
                self.__error_cb(cerr)
            return []
        except requests.exceptions.Timeout:
            log.error('Get seasons timed out!')
            if self.__error_cb:
                self.__error_cb('timeout')
            return []
        except requests.exceptions.RequestException as err:
            log.error(f'Get seasons failed with request error: {err}')
            if self.__error_cb:
                self.__error_cb(err)
            return []

        try:
            data = response.json()
        except ValueError:
            log.error(f'Recieved non-json response: {response.text}')
            if self.__error_cb:
                self.__error_cb(f'Recieved non-json response: {response.text}')
            return []

        try:
            pokes = data['pokemons'] # sic!
        except KeyError:
            log.warning('JSON data is missing key "pokemons"')
            log.debug(data)
            return []

        return self.__apply_filter(pokes)

    def __scraping_loop(self, filters = None):
        """ Repeatedly gets data and calls the callback with it """

        if filters:
            self.__filters = filters

        while self.__running:

            data = self.__get_data()

            if self.__action_cb and len(data):
                self.__action_cb(data)

            time.sleep(self.__delay)

    def start(self, filters, *args):
        """ Runs the scraper by starting a separate thread that runs the scraper loop """

        if self.__running:
            log.debug('Already running')
            return

        self.__running = True

        self.__scraper_thread = Thread(target=self.__scraping_loop, args=args)
        self.__scraper_thread.start()
        log.debug(f'Started with filters: {filters}')

    def stop(self):
        """ Stops the scraper by joining the thread back together """

        if not self.__running:
            log.debug('Scraper is already stopped!')
            return

        self.__running = False

        log.debug('Stopping scraper thread...')
        self.__scraper_thread.join()
        log.debug('Stopped scraper thread!')
        self.__scraper_thread = None

    def update_filters(self, filters):

        self.__filters = filters

    def is_running(self):
        """ Whether the scraper is currently running """
        return self.__running
