#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from secrets import BOT_AUTH_TOKEN, BOT_MYSELF_CHAT_ID
import logging

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from scraper import OredScraper

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

# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""

    scraper.start()

    update.message.reply_text('Scraper started')

def stop(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /stop is issued."""

    scraper.stop()

    update.message.reply_text('Scraper stopped')

def ping(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('pong')


def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('This will show the help stuff')


def echo(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    update.message.reply_text(f'I dont know: "{update.message.text}"')

def on_data_recieved(data):
    log.debug('recv')

    pokes = "\n".join(map(lambda x: x.get('pokemon_name'), data))

    updater.bot.send_message(chat_id=BOT_MYSELF_CHAT_ID, text=f'recieved {pokes}')

def on_error(err):
    log.debug('err')

log.debug('Loading scraper')
scraper = OredScraper(cb=on_data_recieved, ecb=on_error)

def main():
    """Start the bot."""


    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("ping", ping))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # on noncommand i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    log.debug('Starting...')

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

    log.debug('Killed')


if __name__ == '__main__':
    main()