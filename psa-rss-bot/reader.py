#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import os
import re
import signal
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from telegram import ParseMode, Bot
from telegram.error import InvalidToken as TelegramInvalidTokenError
from telegram.ext import Updater

log = logging.getLogger('rss')
log.setLevel(logging.DEBUG)

fh = logging.FileHandler('./rss.log', 'w', 'utf-8')
ch = logging.StreamHandler()

fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S'))

log.addHandler(fh)
log.addHandler(ch)

PSA_FEED = 'https://psarips.uk/feed/'

IGNORE_PATTERN = re.compile(r'psa|x265|hevc|\d{4}', flags=re.IGNORECASE)
ESCAPE_CHARS = re.compile(r'(\(|\)|\[|\]|\.|\=)')
GUID_PATTERN = re.compile(r'\?p\=(?P<guid>\d+)$')

CHAT_ME = 426355102

DB = dict()
previousLast = ''

def shut_down(signal, frame):
    log.info('Killed.')
    sys.exit(0)

def work(bot: Bot):

    log.info('Requesting...')

    try:
        r = requests.get(PSA_FEED, headers={ 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X x.y; rv:42.0) Gecko/20100101 Firefox/42.0' })
    except requests.RequestException as re:
        log.error(f'Failed to get feed because {re}')
        bot.send_message(chat_id=CHAT_ME, text=f'REQUEST FAILED\n{re}', parse_mode=ParseMode.HTML)
        return

    feed = BeautifulSoup(r.content, 'xml') # using lxml strips the CDATA stuff!!!

    # with open('./testfeed.rss', 'r') as rssin:
    #     feed = BeautifulSoup(rssin, 'xml')

    last_build_tag = feed.find('lastBuildDate')

    if not last_build_tag:
        log.error(f'Failed to get feed because cloudflare')
        bot.send_message(chat_id=CHAT_ME, text='*BLOCKED BY CLOUDFLARE*', parse_mode=ParseMode.MARKDOWN_V2)
        return


    last = last_build_tag.string

    if last != previousLast:

        last_build = datetime.strptime(last, '%a, %d %b %Y %H:%M:%S %z')
        last_build_formatted = last_build.astimezone().strftime('%d.%m.%Y %H:%M:%S')
        log.info(f'New feed from {last_build_formatted}')

        lbf = last_build_formatted.replace('.', '\.')

        articles = []

        for item in feed.find_all('item'):

            short_link = item.find('guid').string
            article_name = item.find('title').string
            updated_at = item.find('pubDate').string

            dt = datetime.strptime(updated_at, '%a, %d %b %Y %H:%M:%S %z')
            dt_formatted = dt.astimezone().strftime('%H:%M:%S')

            categories = [ cat.string.strip() for cat in item.find_all('category') if not re.search(IGNORE_PATTERN, cat.string) ]

            m = re.search(GUID_PATTERN, short_link)
            if not m:
                log.warning(f'No guid found for {article_name}, skipping...')
                continue

            guid = m.group('guid')
            entry = DB.get(guid)

            if entry == dt_formatted:
                log.info(f'UNCHANGED: {article_name}')
                continue

            log.info(f'{"NEW" if entry is None else "UPDATED"}: {article_name} ({short_link}) at {dt_formatted}')

            escaped_article_name = re.sub(ESCAPE_CHARS, r'\\\1', article_name)
            articles.append(f'[{escaped_article_name}]({short_link}) um _{dt_formatted}_')

            DB[guid] = dt_formatted

        if len(articles):
            bot.send_message(chat_id=CHAT_ME, text='\n'.join(articles), parse_mode=ParseMode.MARKDOWN_V2)

        previousLast = last
    else:
        log.info('Nothing changed')
        bot.send_message(chat_id=CHAT_ME, text='_Nothing changed_', parse_mode=ParseMode.MARKDOWN_V2)

def main():
    
    try:
        token = os.environ['TELEGRAM_BOT_API_TOKEN']
    except KeyError:
        log.error('No API Token found!')
        sys.exit(-1) 

    try:
        updater = Updater(token)
    except TelegramInvalidTokenError:
        log.error(f'API Token {token} is not valid!')
        sys.exit(-1)

    while True:
        work(updater.bot)
        time.sleep(3600)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, shut_down)
    main()