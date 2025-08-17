from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler,Application

import os

from service.bluesky_service import BlueskyService

STATE_GIVE_USERNAME = 0

list_exists = os.getenv("BLUESKY_LIST", "") != ""
admin_id = int(os.getenv('ADMIN_ID'))

async def add_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of adding a user to the Bluesky list. (main admin command)"""
    if not update.effective_user.id == admin_id:
        await update.message.reply_text('These are not the droids you are looking for ')
    if not list_exists:
        await update.message.reply_text("BLUESKY_LIST environment variable is not set.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Please provide the user handle of the Bluesky user you want to add to the list."
    )
    return STATE_GIVE_USERNAME

async def confirm_added_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm the addition of a user to the Bluesky list."""
    username = update.message.text.strip()
    if not username:
        await update.message.reply_text("Username cannot be empty. Please try again.")
        return STATE_GIVE_USERNAME

    bluesky_service = BlueskyService()
    try:
        bluesky_service.add_to_list(username)
        await update.message.reply_text(f"User @{username} has been added to the list.")
    except Exception as e:
        await update.message.reply_text(f"Failed to add user @{username} to the list: {str(e)}")

    return ConversationHandler.END

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stop the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END
    

def load(app: Application) -> None:

    if not list_exists:
        print("BLUESKY_LIST environment variable is not set.")
        return

    add_to_list_handler = ConversationHandler(
        entry_points=[CommandHandler('addtolist', add_to_list)],
        states={
            STATE_GIVE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_added_to_list)],
        },
        fallbacks=[CommandHandler("stop", stop)]
    )
    app.add_handler(add_to_list_handler)