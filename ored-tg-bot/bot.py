#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from secrets import BOT_AUTH_TOKEN, BOT_MYSELF_CHAT_ID
import logging
import re

from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import NetworkError

from scraper import OredScraper
import time

log = logging.getLogger('ored-tg')
log.setLevel(logging.DEBUG)

fh = logging.FileHandler('./ored.log', 'w', 'utf-8')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

log.addHandler(fh)
log.addHandler(ch)

# Create the Updater and pass it your bot's token.
updater = Updater(BOT_AUTH_TOKEN)

pokes_db = dict()
poke_filter = None
iv_filter = None

def error(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    log.error(f'Update "{update}" caused error "{context.error}"')

# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""

    filters = context.user_data.get('filters', 'defaultfilter')

    scraper.start(filters)

    update.message.reply_text('Scraper started')

def stop(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /stop is issued."""

    scraper.stop()

    update.message.reply_text('Scraper stopped')

def ping(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('pong')

def set_filter(update: Update, context: CallbackContext) -> None:

    new_filters = 'bub'

    context.user_data['filters'] = new_filters
    scraper.update_filters(new_filters)

    update.message.reply_text('Filters updated')

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('/start to start scraping. /stop to stop it /ping to check if server is alive')

def echo(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    update.message.reply_text(f'I dont know: "{update.message.text}", check /help')

def create_html_message(e, now_time):

    # format IVs as hex string if they exist
    if e['individual_attack'] is not None:
        ivs = f"{e['individual_attack']:X}{e['individual_defense']:X}{e['individual_stamina']:X}"
    else:
        ivs = '???'

    if e['level']:
        lvlcp = f"Lvl {e['level']} - <b>{e['cp']} CP</b>"
    else:
        lvlcp = "Lvl ??? - CP ???"

    mytxt = f"{e['pokemon_name']} {lvlcp} ({ivs})\r\nVerified: {'✅' if e['is_verified_despawn'] else '❌'}\r\n"

    despawn_time = time.localtime(e['disappear_time'] / 1000)
    seconds_left = time.mktime(despawn_time) - now_time

    mins, secs = divmod(seconds_left, 60)

    result = f"{mytxt}Bis: <b>{time.strftime('%H:%M:%S', despawn_time)}</b> (Noch <b>{int(mins)} Min {int(secs)}</b>)"

    return result

def send_encounter(poke, nt):

    html_msg = create_html_message(poke, nt)

    try:
        updater.bot.send_message(chat_id=BOT_MYSELF_CHAT_ID, text=html_msg, parse_mode=ParseMode.HTML)
        updater.bot.send_location(chat_id=BOT_MYSELF_CHAT_ID, latitude=poke['latitude'], longitude=poke['longitude'])
        return True
    except NetworkError:
        log.debug('Sending failed')
        return False
    
def on_data_recieved(poke_list):

    now_time = time.mktime(time.localtime())

    for poke in poke_list:

        enc_id = poke.get('encounter_id', '')

        if pokes_db.get(enc_id, False):
            # log.debug('Already known')
            continue

        log.debug(f'New encounter with id {enc_id} added')
        pokes_db[enc_id] = send_encounter(poke, now_time)


def on_error(err):

    updater.bot.send_message(chat_id=BOT_MYSELF_CHAT_ID, text=f'Scraper failed with {err}', parse_mode=ParseMode.HTML)

log.debug('Loading scraper')
scraper = OredScraper(on_data=on_data_recieved, on_error=on_error)

def main():
    """Start the bot."""

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("ping", ping))
    dispatcher.add_handler(CommandHandler("set", set_filter))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # on noncommand i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    dispatcher.add_error_handler(error)

    log.debug('Starting...')

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

    # Stop scraper when bot gets killed
    if scraper.is_running():
        scraper.stop()

    log.debug('Killed')


if __name__ == '__main__':
    main()
