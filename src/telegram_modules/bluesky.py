from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os
import base64

from service.bluesky_service import BlueskyService
from dal import db

#flags
STATE_POST_TEXT, STATE_POST_REPOST, STATE_POST_IMAGE, STATE_ADD_IMAGE, STATE_POST_KEYBOARD_CALLBACK, SELECT_WHAT_TO_UPDATE, UPDATE_TEXT, UPDATE_IMAGE, STATE_REPOST = range(9)

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

def post_preview(context: ContextTypes.DEFAULT_TYPE):
    return f'''
This is a preview of your post:
text: {context.user_data.get('post_text', 'No text')}
images: {len(context.user_data.get('post_images', []))} images
    '''

def post_repost_preview(context: ContextTypes.DEFAULT_TYPE):
    repost_url = context.user_data.get('post_repost', 'No repost URL')
    return f'''
reposting this post:
{repost_url}
    '''

async def bsky_post_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text('You are not authorized to use this command, your id is ' + str(user_id))
        return ConversationHandler.END
    
    text = ""
    if not (context.user_data.get('post_text') or 
            context.user_data.get('post_images')):
        text = "A new post, great! Add text or image (or both)"
    else:
        text = post_preview(context)
        if context.user_data.get('post_repost'):
            text += post_repost_preview(context)
        text += "Add or change text/image, or send the post"
    
    keyboard = [[
        InlineKeyboardButton('Text', callback_data='post_text'), 
        InlineKeyboardButton('Image (new)', callback_data='post_images')
        ],[
        InlineKeyboardButton('Quote Post Link', callback_data='quote_repost'),
        ]]
    
    if context.user_data.get('post_images'):
        keyboard.append([InlineKeyboardButton('Image (add)', callback_data='post_images_add')])
    
    if context.user_data.get('post_text') or context.user_data.get('post_images'):
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

async def bsky_post_repost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text('Please, provide the post URL to quote repost')
    return STATE_POST_REPOST

async def bsky_post_repost_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.startswith('https://bsky.app/'):
        await update.message.reply_text('ehhh, not a Bluesky post URL')
        return await bsky_post_keyboard(update, context)
    post_url = update.message.text
    context.user_data['post_repost'] = post_url
    return await bsky_post_keyboard(update, context)

async def bsky_post_images(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text('Please, provide the image for the post, send one at a time, blame telegram API')
    return STATE_POST_IMAGE

async def bsky_post_images_add(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.edit_message_text('Please, provide the image to add to the post')
    return STATE_ADD_IMAGE

async def bsky_post_images_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')
        context.user_data['post_images'] = [ image_base64 ]

    return await bsky_post_keyboard(update, context)

async def bsky_post_images_keyboard_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        image = await update.message.photo[-1].get_file()
        image_bytes = await image.download_as_bytearray()
        image_base64 = base64.b64encode(image_bytes).decode('ascii')
        
        if 'post_images' not in context.user_data:
            context.user_data['post_images'] = []
        
        context.user_data['post_images'].append(image_base64)
    
    return await bsky_post_keyboard(update, context)

response = '''
Welcome, here's your ID: {userId}, send it to my creator so you can be allowed to post,
meanwhile check what I can do:
/bluesky_post: the basic, I will ask for image and/or text and write a post
/repost: repost a Bluesky post by URL
/update_profile: this allows to set Name, Description, Profile Picture or Banner
/list_posts: I try to keep track of things I posted, this will list and allow to add replies or delete something
/stop: if something broke or you want to stop what you're doing, this is the command
'''

async def bsky_post_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return ConversationHandler.END
    
    text = context.user_data.get('post_text')
    images_base64 = context.user_data.get('post_images')
    if not text and not images_base64:
        await update.message.reply_text('Please, try again and provide text or image.')
        return ConversationHandler.END
    
    link = context.user_data.get('post_repost')
    
    context.user_data.clear()
    service = BlueskyService()
    service.post(text, images_base64, link)
    await update.callback_query.edit_message_text('Post sent')
    return ConversationHandler.END

# endregion

# region list posts

async def list_posts(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return
    
    service = BlueskyService()
    posts = service.list_posts()
    if not posts:
        await update.message.reply_text('No posts found')

    posts_formatted = '\n-------------------\n'.join([f"{post.text}\n /reply_{post.id} /delete_{post.id}" for post in posts])
    await update.message.reply_text(posts_formatted)

# endregion

# region reply post

async def reply_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
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
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return

    text = update.message.text
    post_id = context.user_data['post_id']

    service = BlueskyService()
    service.reply_to_post(post_id, text)
    await update.message.reply_text('Reply sent')
    return ConversationHandler.END

# endregion

# region delete post

async def delete_post(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return

    if len(update.message.text.split('_')) < 2:
        await update.message.reply_text('Please, use the link provided by the list_posts command')
        return
    
    post_id = int(update.message.text.split('_')[-1])

    service = BlueskyService()
    service.delete_post(post_id)
    await update.message.reply_text('Post deleted, probably')

# endregion

# region update profile

async def update_profile(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
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
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
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

# region repost

async def repost_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return ConversationHandler.END
    
    await update.message.reply_text('Please, provide the Bluesky post URL to repost')
    return STATE_REPOST

async def handle_repost(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_config = db.Config.objects(Key = 'AuthorizedUser').first()
    if not auth_config or auth_config.Value != str(user_id):
        await update.message.reply_text(response.replace('{userId}', str(user_id)))
        return ConversationHandler.END
    
    if not update.message.text.startswith('https://bsky.app/'):
        await update.message.reply_text('This doesn\'t look like a valid Bluesky post URL. Please provide a URL like https://bsky.app/profile/username/post/postid')
        return STATE_REPOST
    
    try:
        service = BlueskyService()
        service.repost(update.message.text)
        await update.message.reply_text('Post reposted successfully')
    except ValueError as e:
        await update.message.reply_text(f'Error: {str(e)}')
    except Exception as e:
        await update.message.reply_text(f'An unexpected error occurred: {str(e)}')
    
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
                 CallbackQueryHandler(bsky_post_repost, pattern="^quote_repost$"),
                 CallbackQueryHandler(bsky_post_images, pattern="^post_images$"),
                 CallbackQueryHandler(bsky_post_images_add, pattern="^post_images_add$"),
                 CallbackQueryHandler(bsky_post_send, pattern="^post_send$")],
            STATE_POST_REPOST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bsky_post_repost_keyboard)],
            STATE_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bsky_post_text_keyboard)],
            STATE_POST_IMAGE: [MessageHandler(filters.PHOTO & ~filters.COMMAND, bsky_post_images_keyboard)],
            STATE_ADD_IMAGE: [MessageHandler(filters.PHOTO & ~filters.COMMAND, bsky_post_images_keyboard_add)]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(post_handler)

    repost_handler = ConversationHandler(
        entry_points=[CommandHandler("repost", repost_command)],
        states={
            STATE_REPOST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_repost)]
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(repost_handler)

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