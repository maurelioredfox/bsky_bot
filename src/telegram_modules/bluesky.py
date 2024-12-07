
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os
import base64

from api.bsky_api import Event, EventType, EventData, handle_event
from dal import db

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')

#flags
STATE_POST, STATE_POST_IMAGE, SELECT_WHAT_TO_UPDATE, UPDATE_TEXT, UPDATE_IMAGE = range(5)

async def set_authorized_user(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user.id == int(os.getenv('ADMIN_ID')):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(update.effective_user.id))
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

# region post

async def bsky_post(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END
    
    await update.message.reply_text('Please, provide the text for the post')
    return STATE_POST

async def bsky_post_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['text'] = update.message.text
    await update.message.reply_text('Please, provide the image for the post, or type noimage to post without an image')
    return STATE_POST_IMAGE

async def bsky_post_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END

    text = context.user_data['text']

    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')
    else:
        image_base64 = None
    
    event = Event()
    event.eventType = EventType.Post
    event.data = EventData()
    event.data.text = text
    event.data.image = image_base64
    await handle_event(event)

    await update.message.reply_text('Post sent')
    return ConversationHandler.END

# endregion

# region list posts

async def list_posts(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return
    
    event = Event()
    event.eventType = EventType.List
    event.data = EventData()
    event.data.id = user_id
    await update.message.reply_text('Fetching posts...')
    await handle_event(event) 

# endregion

# region reply post

async def reply_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return

    if len(update.message.text.split('_')) < 2:
        await update.message.reply_text('Please, use the link provided by the list_posts command')
        return
    
    post_id = int(update.message.text.split('_')[-1])
    context.user_data['post_id'] = post_id
    await update.message.reply_text('Please, provide the text for the reply')
    return STATE_POST

async def send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return

    text = update.message.text
    post_id = context.user_data['post_id']

    event = Event()
    event.eventType = EventType.Reply
    event.data = EventData()
    event.data.text = text
    event.data.id = post_id
    await handle_event(event)
    await update.message.reply_text('Reply sent')
    return ConversationHandler.END

# endregion

# region delete post

async def delete_post(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return

    if len(update.message.text.split('_')) < 2:
        await update.message.reply_text('Please, use the link provided by the list_posts command')
        return
    
    post_id = int(update.message.text.split('_')[-1])

    event = Event()
    event.eventType = EventType.Delete
    event.data = EventData()
    event.data.id = post_id
    await handle_event(event)
    await update.message.reply_text('Post deleted, probably')

# endregion

# region update profile

async def update_profile(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
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
    await update.callback_query.message.reply_text('Please, provide the new text')
    return UPDATE_TEXT

async def update_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['update'] = update.callback_query.data
    await update.callback_query.message.reply_text('Please, provide the new image')
    return UPDATE_IMAGE

async def send_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END

    update_type = context.user_data['update']
    text = update.message.text
    image_base64 = None

    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')

    event = Event()
    event.eventType = EventType.Profile_Update
    event.data = EventData()
    
    if update_type == 'name':
        event.data.name = text
    elif update_type == 'description':
        event.data.description = text
    elif update_type == 'image':
        event.data.image = image_base64
    elif update_type == 'banner':
        event.data.banner = image_base64

    await update.message.reply_text('Update sent')
    await handle_event(event)
    return ConversationHandler.END

# endregion

async def stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operation cancelled')
    return ConversationHandler.END

def load(app: Application) -> None:

    app.add_handler(CommandHandler("set_authorized_user", set_authorized_user))

    post_handler = ConversationHandler(
        entry_points=[CommandHandler("bluesky_post", bsky_post)],
        states={
            STATE_POST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bsky_post_image)],
            STATE_POST_IMAGE: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, bsky_post_send),
                MessageHandler(filters.TEXT & filters.Regex('^noimage$'), bsky_post_send)
            ]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(post_handler)

    app.add_handler(CommandHandler("list_posts", list_posts))

    reply_post_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^/reply_[0-9]+$'), reply_to_post)],
        states={
            STATE_POST: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply)]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(reply_post_handler)

    app.add_handler(MessageHandler(filters.Regex('^/delete_[0-9]+$'), delete_post))

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