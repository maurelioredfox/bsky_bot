from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, WebAppInfo
from telegram.ext import ContextTypes, MessageHandler, filters, Application

import base64
import json
import requests

from service.bluesky_service import BlueskyService
from dal import db

response_welcome = '''
Welcome, here's your ID: {userId}, send it to my creator so you can be allowed to post,
meanwhile check what I can do:
/bluesky_post: the basic, I will ask for image and/or text and write a post (can also QRT or reply to a post)
/repost: repost a Bluesky post by URL
/update_profile: this allows to set Name, Description, Profile Picture or Banner
/list_posts: I try to keep track of things I posted, this will list and allow to add replies or delete something
/stop: if something broke or you want to stop what you're doing, this is the command
'''

class WebPostData:
    def __init__(self, text: str, image_urls: list):
        self.text = text
        self.image_urls = image_urls

async def show_web_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response_welcome.replace('{userId}', str(user_id)))
        return

    reply_markup = ReplyKeyboardMarkup.from_button(
            KeyboardButton(
                text="Make a post!",
                web_app=WebAppInfo(url="https://maurelioredfox.github.io/bsky_bot/"),
            )
        )

    await update.message.reply_text("Click the button below to open the Bluesky Post Web App:", reply_markup=reply_markup)

async def handle_web_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #auth
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response_welcome.replace('{userId}', str(user_id)))
        return
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        post_data = WebPostData(
            text=data.get('text', ''),
            image_urls=data.get('images', [])
        )

        images = []
        if post_data.image_urls and len(post_data.image_urls) > 0:
            for url in post_data.image_urls:
                # download image and parse to base64
                response = requests.get(url)
                image_bytes = base64.b64encode(response.content).decode('utf-8')
                images.append(image_bytes)
        
        service = BlueskyService()
        service.post(post_data.text, images, None, None)

        await update.message.reply_text(
            f'Post created successfully!',
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        await update.message.reply_text(f'An unexpected error occurred: {str(e)}', reply_markup=ReplyKeyboardRemove())

def load(app: Application) -> None:
    app.add_handler(MessageHandler(filters.Command("bluesky_post_web"), show_web_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_post))