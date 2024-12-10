from io import BytesIO
import os
from atproto import Client, models
from atproto.exceptions import BadRequestError
import base64
from dal import db
from PIL import Image

from telegram_modules.bluesky_responses import ResponseData, ResponseEvent, ResponseType, handle_response

def update_profile(name: str, description: str, photo, banner):
    client = Client()
    client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])

    try:
        current_profile_record = client.app.bsky.actor.profile.get(client.me.did, 'self')
        current_profile = current_profile_record.value
        swap_record_cid = current_profile_record.cid
    except BadRequestError:
        current_profile = swap_record_cid = None

    old_description = old_display_name = None
    if current_profile:
        old_description = current_profile.description
        old_display_name = current_profile.display_name

    # set new values to update
    new_description = description
    new_display_name = name 
    new_avatar = new_banner = None

    if photo:
        # Decode the base64 encoded photo
        photo_data = base64.b64decode(photo)
        new_avatar = client.upload_blob(photo_data).blob

    if banner:
        # Decode the base64 encoded banner
        banner_data = base64.b64decode(banner)
        new_banner = client.upload_blob(banner_data).blob

    client.com.atproto.repo.put_record(
        models.ComAtprotoRepoPutRecord.Data(
            collection=models.ids.AppBskyActorProfile,
            repo=client.me.did,
            rkey='self',
            swap_record=swap_record_cid,
            record=models.AppBskyActorProfile.Record(
                avatar=new_avatar or current_profile.avatar,
                banner=new_banner or current_profile.banner,
                description=new_description or old_description,
                display_name=new_display_name or old_display_name,
            ),
        )
    )

async def list_posts(chat_id: int):
    #pick last 10
    posts = db.Posts.objects().order_by('-id')[:10]
    event = ResponseEvent()
    event.chat_id = chat_id
    event.eventType = ResponseType.List
    event.data = ResponseData()
    event.data.posts = posts
    await handle_response(event)

def post(text: str, photo: str):
    client = Client()
    client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])

    if photo:
        # Decode the base64 encoded photo
        photo_data = base64.b64decode(photo)
        image: Image = Image.open(BytesIO(photo_data))
        aspect_ratio = models.AppBskyEmbedDefs.AspectRatio(height=image.height, width=image.width)
        post = client.send_image(
            text=text,
            image=photo_data,
            image_alt=f'{text or "no post text"} - sent from a Python bot',
            image_aspect_ratio= aspect_ratio
        )
        db.Posts(text=text, cid=post.cid, uri=post.uri).save()
        return
    post = client.send_post(text)
    db.Posts(text=text, cid=post.cid, uri=post.uri).save()

def delete_post(Id: int):
    client = Client()
    client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])
    post = db.Posts.objects(id=Id).first()
    if not post:
        return
    client.delete_post(post.uri)
    post.delete()

def reply_to_post(Id: int, text: str):
    client = Client()
    client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])
    post: db.Posts = db.Posts.objects(id=Id).first()
    if not post:
        return
    root_post = post.root or post
    parent_ref = models.ComAtprotoRepoStrongRef.Main(cid=post.cid, uri=post.uri)
    root_ref = models.ComAtprotoRepoStrongRef.Main(cid=root_post.cid, uri=root_post.uri)

    reply_post = client.send_post(text, reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref))
    db.Posts(text=text, cid=reply_post.cid, uri=reply_post.uri, parent=post, root=root_post).save()

class EventType:
    Post = 'post'
    Delete = 'delete'
    Reply = 'reply'
    List = 'list'
    Profile_Update = 'profile_update'

class EventData:
    text: str = None
    image: str = None #(base64)
    name: str = None
    description: str = None
    banner: str = None #(base64)
    id: int = None

class Event:
    eventType: EventType
    data: EventData

async def handle_event(event: Event):
    try:
        match event.eventType:
            case EventType.Post:
                text = event.data.text
                if not text and not event.data.image:
                    raise ValueError('Text or Image is required for a post event')
                post(text, event.data.image)

            case EventType.List:
                await list_posts(event.data.id)

            case EventType.Delete:
                if not event.data.id:
                    raise ValueError('Id is required for a delete event')
                delete_post(event.data.id)

            case EventType.Reply:
                text = event.data.text
                if not text:
                    raise ValueError('Text is required for a reply event')
                if not event.data.id:
                    raise ValueError('Id is required for a reply event')
                reply_to_post(event.data.id, text)

            case EventType.Profile_Update:
                if not event.data.name and not event.data.description and not event.data.image and not event.data.banner:
                    raise ValueError('At least one of name, description, image, or banner is required for a profile update event')
                update_profile(
                    event.data.name,
                    event.data.description,
                    event.data.image,
                    event.data.banner
                )

            case _:
                raise ValueError(f'Unknown event type: {event.eventType}')
    except Exception as e:
        print(f'Error handling event: {e}')