from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os
import base64
import json

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
    def __init__(self, text: str, image_data: str | None):
        self.text = text
        self.images = []

async def handle_web_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response_welcome.replace('{userId}', str(user_id)))
        return

    if len(context.args) < 1:
        await update.message.reply_text('Something wrong happened.')
        return

    try:
        post_data_json = ' '.join(context.args)
        post_data_dict = json.loads(post_data_json)
        post_data = WebPostData(
            text=post_data_dict.get('text', ''),
            image_data=post_data_dict.get('image_data')
        )
    except json.JSONDecodeError:
        await update.message.reply_text('Something wrong happened.')
        return

    bluesky_service = BlueskyService()
    images = []
    if post_data.image_data:
        image_bytes = base64.b64decode(post_data.image_data)
        images.append(image_bytes)

    try:
        post_response = await bluesky_service.create_post(
            text=post_data.text,
            images=images if images else None
        )
        await update.message.reply_text(f'Post created successfully! View it at: {post_response["post_url"]}')
    except Exception as e:
        await update.message.reply_text(f'Failed to create post: {str(e)}')

def load(app: Application) -> None:
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_post))