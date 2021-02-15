#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import requests
import logging
from threading import Event, Thread
import time
import re
from datetime import datetime
from pytz import timezone

from telegram.error import NetworkError
from telegram import ParseMode, Bot

from secrets import DOMAIN, API_ENDPOINT

log = logging.getLogger('ored-tg')

class OredScraper:

    def __init__(self, tg_bot: Bot, chat_id: str, delay: int=5):
        self.__running = False
        self.__sess = requests.Session()
        self.__sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
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

        self.__pokes_db = dict()
        
        self.__scraper_thread = None
        self.__remover_thread = None
        self.__stopper = Event()

        self.__tg_bot = tg_bot
        self.__CHAT_ID = chat_id

        # check for expired encounters every this many seconds
        self.CLEANUP_EXPIRED_INTERVAL = 600

        self.__filters = None
        self.__tz = timezone('Europe/Berlin')

        self.__setup()

    def __setup(self) -> None:
        """ Calls the site once to get the token and setup the cookies """

        r = self.__sess.get(f'{DOMAIN}/')
        m = re.search(r'var token = \'(\S{42,48})\';', r.text)

        if m:
            log.debug(f'Token set to {m[1]}')
            self.__payload['token'] = m[1]
            self.__tg_bot.send_message(chat_id=self.__CHAT_ID, text='💪🏻 Scraper loaded 💪🏻', parse_mode=ParseMode.HTML)
        else:
            log.error(f'No token found!')
            self.__tg_bot.send_message(chat_id=self.__CHAT_ID, text='❌ No token found! ❌', parse_mode=ParseMode.HTML)

    def __apply_filter(self, data):

        return data

    def __get_data(self):
        """ Queries data from the endpoint and returns it as a list"""

        try:
            response = self.__sess.post(f'{DOMAIN}/{API_ENDPOINT}', data=self.__payload, headers=self.__hds, timeout=10)
            response.raise_for_status()

        except requests.HTTPError as httpe:
            self.__on_error(f'POST failed with http error: {httpe}')
            return []
        except requests.exceptions.ConnectionError as cerr:
            self.__on_error(f'POST failed with network error: {cerr}')
            return []
        except requests.exceptions.Timeout:
            self.__on_error(f'POST timed out')
            return []
        except requests.exceptions.RequestException as err:
            self.__on_error(f'POST failed with request error: {err}')
            return []

        try:
            data = response.json()
        except ValueError:
            self.__on_error(f'Recieved non-json response: {response.text}')
            return []

        try:
            pokes = data['pokemons'] # sic!
        except KeyError:
            log.warning('JSON data is missing key "pokemons"')
            log.debug(data)
            return []

        return self.__apply_filter(pokes)

    def __send_encounter(self, poke, now: int):

        # format IVs as hex string if they exist
        if poke['individual_attack'] is not None:
            ivs = f"{poke['individual_attack']:X}{poke['individual_defense']:X}{poke['individual_stamina']:X}"
        else:
            ivs = '???'

        if poke['level']:
            lvlcp = f"Lvl {poke['level']} - <b>{poke['cp']} CP</b>"
        else:
            lvlcp = "Lvl ??? - CP ???"

        mytxt = f"{poke['pokemon_name']} {lvlcp} ({ivs})\r\nVerified: {'✅' if poke['is_verified_despawn'] else '❌'}\r\n"

        despawn_time = poke['disappear_time'] / 1e3

        mins, secs = divmod(int(despawn_time) - now, 60)

        html_msg = f"{mytxt}Bis: <b>{datetime.fromtimestamp(despawn_time, tz=self.__tz).strftime('%H:%M:%S')}</b> (Noch <b>{int(mins)} Min {int(secs)}</b>)"

        try:
            self.__tg_bot.send_message(chat_id=self.__CHAT_ID, text=html_msg, parse_mode=ParseMode.HTML)
            self.__tg_bot.send_location(chat_id=self.__CHAT_ID, latitude=poke['latitude'], longitude=poke['longitude'])

            self.__pokes_db[poke['encounter_id']] = True

        except NetworkError:
            log.debug('Sending failed')
            self.__pokes_db[poke['encounter_id']] = False

    def __on_error(self, err):

        log.error(err)
        self.__tg_bot.send_message(chat_id=self.__CHAT_ID, text=f'Scraper failed with {err}', parse_mode=ParseMode.HTML)

    def __scraping_loop(self, filters = None):
        """ Repeatedly gets data and calls the callback with it """

        if filters:
            self.__filters = filters

        while self.__running:

            filtered_pokes = self.__get_data()
            now_time = int(datetime.now(self.__tz).timestamp())

            for poke in filtered_pokes:

                enc_id = poke.get('encounter_id', '')

                # already in db, ignore
                if self.__pokes_db.get(enc_id, False):
                    continue

                log.debug(f'New encounter with id {enc_id} added')
                self.__send_encounter(poke, now_time)

            time.sleep(self.__delay)

    def __removing_loop(self):

        # repeat until stop flag is set
        while not self.__stopper.wait(self.CLEANUP_EXPIRED_INTERVAL):
            now = int(datetime.now(self.__tz).timestamp())
            log.debug('Removing...')

            # iterate through database and remove expired encounters
            for enc_id, p_info in self.__pokes_db.copy().items():
                if p_info['despawn'] - now < 5:
                    del self.__pokes_db[enc_id]

    def start(self, filters, *args):
        """ Runs the scraper by starting a separate thread that runs the scraper loop """

        if self.__running:
            log.debug('Already running')
            return

        self.__stopper.clear()
        self.__remover_thread = Thread(target=self.__removing_loop)
        self.__remover_thread.start()

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

        self.__stopper.set()

        log.debug('Stopping cleaner thread...')
        self.__remover_thread.join()
        log.debug('Stopped cleaner thread!')
        self.__remover_thread = None

        self.__pokes_db = dict()

    def update_filters(self, filters):

        self.__filters = filters

    def get_pokes_db_size(self):
        return len(self.__pokes_db)

    def is_running(self):
        """ Whether the scraper is currently running """
        return self.__running
