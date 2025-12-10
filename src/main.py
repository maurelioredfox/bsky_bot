import os
from telegram import Update
from telegram.ext import ApplicationBuilder
import telegram_modules.bluesky_profile as bluesky_profile
import telegram_modules.bsky_list as bsky_list
import telegram_modules.bluesky_post_web as bluesky_post_web
import telegram_modules.bluesky_post as bluesky_post

TOKEN = os.getenv('TELEGRAM_TOKEN_BSKY') 

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    bsky_list.load(app)
    bluesky_post_web.load(app)
    bluesky_post.load(app)
    bluesky_profile.load(app)

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()