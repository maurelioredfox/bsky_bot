from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os
import base64

from service.bluesky_service import BlueskyService
from dal import db

#flags
STATE_POST_TEXT, STATE_POST_REPOST, STATE_POST_IMAGE, STATE_ADD_IMAGE, STATE_POST_KEYBOARD_CALLBACK, SELECT_WHAT_TO_UPDATE, UPDATE_TEXT, UPDATE_IMAGE, STATE_REPOST = range(9)

response_welcome = '''
Welcome, here's your ID: {userId}, send it to my creator so you can be allowed to post,
meanwhile check what I can do:
/bluesky_post: the basic, I will ask for image and/or text and write a post (can also QRT or reply to a post)
/repost: repost a Bluesky post by URL
/update_profile: this allows to set Name, Description, Profile Picture or Banner
/list_posts: I try to keep track of things I posted, this will list and allow to add replies or delete something
/stop: if something broke or you want to stop what you're doing, this is the command
'''

async def set_authorized_user(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user.id == int(os.getenv('ADMIN_ID')):
        await update.message.reply_text('these are not the droids you are looking for ')
        return
    if len(update.message.text.split()) < 2:
        await update.message.reply_text('Please, provide the user id')
        return
    user_id = update.message.text.split()[1]

    config = db.Config.objects(Key = 'AuthorizedUser').first()

    newConfig = db.Config() if not config else config
    newConfig.Key = 'AuthorizedUser'
    newConfig.Value = user_id
    newConfig.save()

    await update.message.reply_text(f'Authorized user set to {user_id}')

# region update profile

async def update_profile(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response_welcome.replace('{userId}', str(user_id)))
        return ConversationHandler.END
    
    keyboard = [[
        InlineKeyboardButton('Name', callback_data='name'), 
        InlineKeyboardButton('Description', callback_data='description'), 
        InlineKeyboardButton('Image', callback_data='image'), 
        InlineKeyboardButton('Banner', callback_data='banner')]]

    await update.message.reply_text('What do you want to update?', reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_WHAT_TO_UPDATE

async def update_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['update'] = update.callback_query.data
    await update.callback_query.edit_message_text('Please, provide the new text')
    return UPDATE_TEXT

async def update_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['update'] = update.callback_query.data
    await update.callback_query.edit_message_text('Please, provide the new image')
    return UPDATE_IMAGE

async def send_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response_welcome.replace('{userId}', str(user_id)))
        return ConversationHandler.END

    update_type = context.user_data['update']
    text = update.message.text
    image_base64 = None

    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')

    service = BlueskyService()
    if update_type == 'name':
        service.update_profile(name=text)
    elif update_type == 'description':
        service.update_profile(description=text)
    elif update_type == 'image':
        service.update_profile(photo=image_base64)
    elif update_type == 'banner':
        service.update_profile(banner=image_base64)
        
    await update.message.reply_text('Update sent')
    return ConversationHandler.END

# endregion

async def stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operation cancelled')
    return ConversationHandler.END

def load(app: Application) -> None:

    app.add_handler(CommandHandler("set_authorized_user", set_authorized_user))

    update_profile_handler = ConversationHandler(
        entry_points=[CommandHandler("update_profile", update_profile)],
        states={
            SELECT_WHAT_TO_UPDATE: [CallbackQueryHandler(update_text, pattern="^(name|description)$"), 
                                    CallbackQueryHandler(update_image, pattern="^(image|banner)$")],
            UPDATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_update)],
            UPDATE_IMAGE: [MessageHandler(filters.PHOTO & ~filters.COMMAND, send_update)]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(update_profile_handler)