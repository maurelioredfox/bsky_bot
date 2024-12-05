from dataclasses import dataclass
import os
from atproto import Client, models
from atproto.exceptions import BadRequestError
from enum import Enum
import base64

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

def post(text: str, photo: str):
    client = Client()
    client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])

    if photo:
        # Decode the base64 encoded photo
        photo_data = base64.b64decode(photo)
        client.send_image(
            text=text,
            image=photo_data,
            image_alt=f'{text} - sent from a Python bot',
        )
        return

    client.send_post(text)

class EventType:
    Post = 'post'
    Profile_Update = 'profile_update'

class EventData:
    text: str
    image: str #(base64)
    name: str
    description: str
    banner: str #(base64)

class Event:
    eventType: EventType
    data: EventData

def handle_event(event: Event):
    try:
        if event.eventType == EventType.Post:
            text = event.data.text
            if not text:
                raise ValueError('Text is required for a post event')
            post(text, event.data.image)
        elif event.eventType == EventType.Profile_Update:
            update_profile(
                event.data.name,
                event.data.description,
                event.data.image,
                event.data.banner
            )
        else:
            raise ValueError(f'Unknown event type: {event.eventType}')
    except Exception as e:
        print(f'Error handling event: {e}')