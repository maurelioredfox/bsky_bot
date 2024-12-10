
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os
import base64

from api.bsky_api import Event, EventType, EventData, handle_event
from dal import db

#flags
STATE_POST_TEXT, STATE_POST_IMAGE, STATE_POST_KEYBOARD_CALLBACK, SELECT_WHAT_TO_UPDATE, UPDATE_TEXT, UPDATE_IMAGE = range(6)

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

async def bsky_post_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END
    
    text = ""
    if not (context.user_data.get('post_text') or context.user_data.get('post_image')):
        text = "A new post, right? Add text or image, or both ..."
    else:
        text = "Add or change text/image, or send the post"
    
    keyboard = [[
        InlineKeyboardButton('Text', callback_data='post_ext'), 
        InlineKeyboardButton('Image', callback_data='post_image')
        ]]
    
    if context.user_data.get('post_text') or context.user_data.get('post_image'):
        keyboard.append([InlineKeyboardButton('Send', callback_data='post_send')])

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else :
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_POST_KEYBOARD_CALLBACK

async def bsky_post_text(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text('Please, provide the text for the post')
    return STATE_POST_TEXT

async def bsky_post_text_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['post_text'] = update.message.text
    return await bsky_post_keyboard(update, context)

async def bsky_post_image(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text('Please, provide the image for the post')
    return STATE_POST_IMAGE

async def bsky_post_image_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')
        context.user_data['post_image'] = image_base64

    return await bsky_post_keyboard(update, context)

async def bsky_post_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END
    
    text = context.user_data.get('post_text')
    image_base64 = context.user_data.get('post_image')
    if not text and not image_base64:
        await update.message.reply_text('Please, try again and provide text or image.')
        return ConversationHandler.END
    context.user_data.clear()

    event = Event()
    event.eventType = EventType.Post
    event.data = EventData()
    event.data.text = text
    event.data.image = image_base64
    await handle_event(event)

    await update.callback_query.edit_message_text('Post sent')
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
    return STATE_POST_TEXT

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

    await handle_event(event)
    await update.message.reply_text('Update sent')
    return ConversationHandler.END

# endregion

async def stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operation cancelled')
    return ConversationHandler.END

def load(app: Application) -> None:

    app.add_handler(CommandHandler("set_authorized_user", set_authorized_user))

    post_handler = ConversationHandler(
        entry_points=[CommandHandler("bluesky_post", bsky_post_keyboard)],
        states={
            STATE_POST_KEYBOARD_CALLBACK: 
                [CallbackQueryHandler(bsky_post_text, pattern="^post_text$"),
                 CallbackQueryHandler(bsky_post_image, pattern="^post_image$"),
                 CallbackQueryHandler(bsky_post_send, pattern="^post_send$")],
            STATE_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bsky_post_text_keyboard)],
            STATE_POST_IMAGE: [MessageHandler(filters.PHOTO & ~filters.COMMAND, bsky_post_image_keyboard)]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(post_handler)

    app.add_handler(CommandHandler("list_posts", list_posts))

    reply_post_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^/reply_[0-9]+$'), reply_to_post)],
        states={
            STATE_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply)]
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