import os
from telegram.ext import ApplicationBuilder
import telegram_modules.bluesky as bluesky
import telegram_modules.bsky_list as bsky_list

TOKEN = os.getenv('TELEGRAM_TOKEN_BSKY') 

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    bluesky.load(app)
    bsky_list.load(app)

    app.run_polling()

if __name__ == '__main__':
    main()