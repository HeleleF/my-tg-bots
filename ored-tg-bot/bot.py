#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
from secrets import BOT_AUTH_TOKEN, BOT_MYSELF_CHAT_ID

from telegram import Update
from telegram.ext import (CallbackContext, CommandHandler, Filters,
                          MessageHandler, Updater)

from scraper import OredScraper

log = logging.getLogger('ored-tg')
log.setLevel(logging.DEBUG)

#fh = logging.FileHandler('./ored.log', 'w', 'utf-8')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
#fh.setFormatter(formatter)
ch.setFormatter(formatter)

#log.addHandler(fh)
log.addHandler(ch)

# Create the Updater and pass it your bot's token.
updater = Updater(BOT_AUTH_TOKEN)

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

def db_size(update: Update, context: CallbackContext) -> None:

    size = scraper.get_pokes_db_size()
    update.message.reply_text(f'Pokes in db: {size}')

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

log.debug('Loading scraper')
scraper = OredScraper(tg_bot=updater.bot, chat_id=BOT_MYSELF_CHAT_ID)

def main():
    """Start the bot."""

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("size", db_size))
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
