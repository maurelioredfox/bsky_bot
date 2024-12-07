from telegram import Bot
from telegram.ext import Application


from dataclasses import dataclass

class StaticBot:
    BOT: Bot = None

class ResponseType:
    List = 'list'

class ResponseData:
    posts: list = None

class ResponseEvent:
    chat_id: int
    eventType: ResponseType
    data: ResponseData

async def list_posts(chat_id: int, posts: list ):
    if not posts:
        raise ValueError('No posts found')
    posts_formatted = '\n-------------------\n'.join([f"{post.text}\n /reply_{post.id} /delete_{post.id}" for post in posts])
    await StaticBot.BOT.send_message(chat_id, posts_formatted)

async def handle_response(event: ResponseEvent):
    try:
        match event.eventType:
            case ResponseType.List:
                await list_posts(event.chat_id, event.data.posts)
    except ValueError as e:
        print(e)

def load(app: Application) -> None:
    StaticBot.BOT = app.bot