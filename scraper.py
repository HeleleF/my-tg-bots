#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import requests
import logging
from threading import Thread
import time
import re

from secrets import DOMAIN, API_ENDPOINT

log = logging.getLogger('ored-scraper')
log.setLevel(logging.DEBUG)

fh = logging.FileHandler('./ored-scraper.log', 'w', 'utf-8')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

log.addHandler(fh)
log.addHandler(ch)

class OredScraper:

    def __init__(self, cb=None, ecb=None, delay=3):
        self.running = False
        self.sess = requests.Session()
        self.sess.headers.update({
            'User-Agent': 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
        })
        self.delay = delay
        self.hds = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': DOMAIN,
            'Referer': f'{DOMAIN}/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        self.payload = {
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
                "minIV": "91",
                "prevMinIV": "91",
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
                "eids": "0"
        }
        self.setup()
        self.thr = None
        self.action_cb = cb
        self.error_cb = ecb

    def setup(self):
        r = self.sess.get(f'{DOMAIN}/')
        m = re.search(r'var token = \'(\S{42,48})\';', r.text)

        if m:
            log.debug(f'Token set to {m[1]}')
            self.payload['token'] = m[1]

    def get_data(self):

        try:
            response = self.sess.post(f'{DOMAIN}/{API_ENDPOINT}', data=self.payload, headers=self.hds, timeout=10)
            response.raise_for_status()

        except requests.HTTPError as httpe:
            log.error(f'Get seasons failed with http error: {httpe}')
            if self.error_cb:
                self.error_cb(httpe)
            return []
        except requests.exceptions.ConnectionError as cerr:
            log.error(f'Get seasons failed with network problems: {cerr}')
            if self.error_cb:
                self.error_cb(cerr)
            return []
        except requests.exceptions.Timeout:
            log.error('Get seasons timed out!')
            if self.error_cb:
                self.error_cb('timeout')
            return []
        except requests.exceptions.RequestException as err:
            log.error(f'Get seasons failed with request error: {err}')
            if self.error_cb:
                self.error_cb(err)
            return []

        try:
            data = response.json()
        except ValueError:
            log.error(f'Recieved non-json response: {response.text}')
            if self.error_cb:
                self.error_cb(data)
            return []

        pokes = data.get('pokemons')

        if not pokes:
            log.warning('Missing pokemons?')
            return []

        return pokes

    def scraping_loop(self, *args):

        while self.running:

            data = self.get_data()
            log.debug(f'ACTION {len(data)}')

            if self.action_cb:
                self.action_cb(data)

            time.sleep(self.delay)

    def start(self, *args):

        if self.running:
            log.debug('Already running')
            return

        self.running = True

        self.thr = Thread(target=self.scraping_loop, args=args)
        self.thr.start()
        log.debug('Started')

    def stop(self):

        if not self.running:
            log.debug('Already stopped')
            return

        self.running = False

        log.debug('Stopping...')
        self.thr.join()
        log.debug('Stopped')
        self.thr = None

