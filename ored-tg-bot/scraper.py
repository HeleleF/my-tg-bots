#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import re
import time
from datetime import datetime, timedelta
from secrets import API_ENDPOINT, DOMAIN
from threading import Event, Thread
from typing import List

import dateutil.tz
import requests
from telegram import Bot, ParseMode
from telegram.error import NetworkError

log = logging.getLogger('ored-tg')

class OredScraper:

    def __init__(self, tg_bot: Bot, chat_id: str, delay: int=5) -> None:
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

        self.__filters_string = 'iv=97&exiv=113,149'

        self.__pokes_db = dict()
        
        self.__scraper_thread = None
        self.__remover_thread = None
        self.__stopper = Event()

        self.__tg_bot = tg_bot
        self.__CHAT_ID = chat_id

        # check for expired encounters every this many seconds
        self.CLEANUP_EXPIRED_INTERVAL = 600

        self.__tz = dateutil.tz.gettz('Europe/Berlin')

        self.__token_expiration_date = None

        self.__update_token()

    def __update_token(self) -> bool:
        """ Calls the site once to get the token and setup the cookies """

        self.__sess.cookies.clear()

        r = self.__sess.get(f'{DOMAIN}/')
        m = re.search(r'var token = \'(\S{42,48})\';', r.text)

        if not m:
            self.__log_msg(f'No token found!', is_err=True)
            return False

        old_token = self.__payload.get('token', None)
        self.__payload['token'] = m[1]

        # midnight today
        self.__token_expiration_date = datetime.now(self.__tz).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(1)

        if old_token:
            self.__log_msg(f'TOKEN UPDATED: "{old_token}" -> "{m[1]}"')
        else:
            self.__log_msg(f'TOKEN SET: "{m[1]}"')
        return True

    def __check_token(self) -> bool:
        """ Returns TRUE if token expired and was successfully updated to a new one

        Returns FALSE if token is not expired

        Returns FALSE if token expired and was NOT updated to a new one because of errors
        """

        now = datetime.now(self.__tz)

        if (self.__token_expiration_date - now).total_seconds() < 0:
            log.debug('Token needs update!')
            return self.__update_token()
        return False

    def __get_data(self) -> List:
        """ Queries data from the endpoint and returns it as a list"""

        try:
            response = self.__sess.post(f'{DOMAIN}/{API_ENDPOINT}', data=self.__payload, headers=self.__hds, timeout=10)
            response.raise_for_status()

        except requests.HTTPError as httpe:

            if response.status_code == 400:
                is_updated = self.__check_token()

                if not is_updated:
                    # either token is not expired -> BAD, because we got a 400 error and we dont know why
                    # or token expired and not updated -> BAD, we failed to get a new one
                    self.__log_msg(f'Recieved {httpe}\n Failed to update the token OR unknown 400. Either way, stop scanning to be safe.', is_err=True)
                    self.__running = False
                    self.__stopper.set()

            else:
                self.__log_msg(f'Stop scanning because: {httpe}', is_err=True)
                self.__running = False
                self.__stopper.set()
            return []
        except requests.exceptions.ConnectionError as cerr:
            self.__log_msg(f'POST failed with network error: {cerr}', is_err=True)
            return []
        except requests.exceptions.Timeout:
            self.__log_msg(f'POST timed out', is_err=True)
            return []
        except requests.exceptions.RequestException as err:
            self.__log_msg(f'POST failed with request error: {err}', is_err=True)
            return []

        try:
            data = response.json()
        except ValueError:
            self.__log_msg(f'Recieved non-json response: {response.text}', is_err=True)
            return []

        try:
            pokes = data['pokemons'] # sic!
        except KeyError:
            self.__log_msg('JSON data is missing key "pokemons"')
            log.debug(data)
            return []

        return pokes

    def __send_encounter(self, poke, now: int) -> None:

        # format IVs as hex string if they exist
        if poke['individual_attack'] is not None:
            ivs = f"{poke['individual_attack']:X}{poke['individual_defense']:X}{poke['individual_stamina']:X}"
        else:
            ivs = '???'

        if poke['level']:
            lvlcp = f"Lvl {poke['level']} - <b>{poke['cp']} CP</b>"
        else:
            lvlcp = "Lvl ??? - CP ???"

        header = f"{poke['pokemon_name']} {lvlcp} ({ivs})\r\nVerified: {'✅' if poke['is_verified_despawn'] else '❌'}\r\n"

        despawn_time = poke['disappear_time'] / 1e3
        mins, secs = divmod(int(despawn_time) - now, 60)

        html_msg = f"{header}Bis: <b>{datetime.fromtimestamp(despawn_time, tz=self.__tz).strftime('%H:%M:%S')}</b> (Noch <b>{int(mins)} Min {int(secs)}</b>)"

        try:
            self.__tg_bot.send_message(chat_id=self.__CHAT_ID, text=html_msg, parse_mode=ParseMode.HTML)
            self.__tg_bot.send_location(chat_id=self.__CHAT_ID, latitude=poke['latitude'], longitude=poke['longitude'])

            # store despawn time in ms
            # this lets us remove expired encounters
            self.__pokes_db[poke['encounter_id']] = despawn_time

        except NetworkError:
            log.debug('Sending failed')

    def __log_msg(self, msg_or_err, is_err = False) -> None:

        if is_err:
            log.error(msg_or_err)
        else:
            log.debug(msg_or_err)

        self.__tg_bot.send_message(
            chat_id=self.__CHAT_ID,
            text=f'❌❌❌\n{msg_or_err}\n❌❌❌' if is_err else f'DEBUG:\n{msg_or_err}',
            parse_mode=ParseMode.HTML
        )

    def __scraping_loop(self, filters = None) -> None:
        """ Repeatedly gets data and sends messages with it """

        if filters:
            self.update_filters(filters)

        while self.__running:

            now_time = int(datetime.now(self.__tz).timestamp())

            for poke in self.__get_data():

                enc_id = poke.get('encounter_id', '')

                # already in db, ignore
                if self.__pokes_db.get(enc_id, False):
                    continue

                log.debug(f'New encounter with id {enc_id} added')
                self.__send_encounter(poke, now_time)

            time.sleep(self.__delay)

    def __removing_loop(self) -> None:
        """
        Loops through the poke db and deletes
        expired encounters 
        
        (for simplicity, we consider
        encounters with less than 5 seconds remaining time to
        be expired, since we couldnt get to them anyway)
        """

        # repeat until stop flag is set
        while not self.__stopper.wait(self.CLEANUP_EXPIRED_INTERVAL):
            now = int(datetime.now(self.__tz).timestamp())
            log.debug('Removing...')

            # iterate through database and remove expired encounters
            for enc_id, despawn_time in self.__pokes_db.copy().items():
                if despawn_time - now < 5:
                    del self.__pokes_db[enc_id]

    def start(self, *args) -> None:
        """ Runs the scraper by starting a separate thread that runs the scraper loop """

        if self.__running:
            self.__log_msg('Already running')
            return

        self.__check_token()

        self.__stopper.clear()
        self.__remover_thread = Thread(target=self.__removing_loop)
        self.__remover_thread.start()

        self.__running = True
        self.__scraper_thread = Thread(target=self.__scraping_loop, args=args)
        self.__scraper_thread.start()
        log.debug(f'Started')

    def stop(self) -> None:
        """ Stops the scraper by joining the threads back together """

        if not self.__running:
            self.__log_msg('Scraper is already stopped!')
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

    def update_filters(self, filters: str) -> None:
        """Updates the filter

        Currently, this is destructive, so new values are
        not merged with old ones.
        """

        log.debug(f'Updating filters to {filters}')

        parts = filters.split('&')

        for part in parts:
            value, key = part.split('=')

            if value == 'iv':
                self.__payload['prevMinIV'] = self.__payload['minIV']
                self.__payload['minIV'] = key.strip()
            elif value == 'exiv':
                self.__payload['exMinIV'] = key.strip()
            else:
                log.debug(f'Dont know filter: "{part}", ignoring...')

        self.__filters_string = filters

    def get_current_filters(self) -> str:
        """Returns current filter as a string
        (no formatting)
        """
        return self.__filters_string

    def get_pokes_db_size(self) -> int:
        """ Returns the size of the poke db
        """

        return len(self.__pokes_db)

    def is_running(self) -> bool:
        """ Whether the scraper is currently running """
        return self.__running
