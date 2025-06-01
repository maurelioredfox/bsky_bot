from io import BytesIO
import os
from atproto import Client, models
from atproto.exceptions import BadRequestError
import base64
from dal import db
from PIL import Image

class BlueskyService():
    def __init__(self):
        self.client = Client()
        self.client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])

    def update_profile(self, name: str = None, description: str = None, photo = None, banner = None):
        if not name and not description and not photo and not banner:
            raise ValueError('At least one field must be provided to update the profile')

        try:
            current_profile_record = self.client.app.bsky.actor.profile.get(self.client.me.did, 'self')
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
            new_avatar = self.client.upload_blob(photo_data).blob

        if banner:
            # Decode the base64 encoded banner
            banner_data = base64.b64decode(banner)
            new_banner = self.client.upload_blob(banner_data).blob

        self.client.com.atproto.repo.put_record(
            models.ComAtprotoRepoPutRecord.Data(
                collection=models.ids.AppBskyActorProfile,
                repo=self.client.me.did,
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

    def list_posts(self):
        #pick last 10
        posts = db.Posts.objects().order_by('-id')[:10]
        return posts
    
    def post(self, text: str, photo):
        if not text and not photo:
            raise ValueError('At least one field must be provided to create a post')

        if photo and len(photo) > 0:
            
            photos = []
            aspect_ratios = []

            for p in photo:
                # Decode the base64 encoded photo
                photo_data = base64.b64decode(p)
                image: Image = Image.open(BytesIO(photo_data))
                aspect_ratio = models.AppBskyEmbedDefs.AspectRatio(height=image.height, width=image.width)
                aspect_ratios.append(aspect_ratio)
                photos.append(photo_data)


            post = self.client.send_images(
                text = text or "",
                images = photos,
                image_aspect_ratios = aspect_ratios
            )
            db.Posts(text=text, cid=post.cid, uri=post.uri).save()
            return

        post = self.client.send_post(text)
        db.Posts(text=text, cid=post.cid, uri=post.uri).save()

    def delete_post(self, post_id: int):
        if not post_id:
            raise ValueError('Post ID is required to delete a post')
        post = db.Posts.objects(id=post_id).first()
        if not post:
            raise ValueError('Post not found')
        self.client.delete_post(post.cid)
        post.delete()

    def reply_to_post(self, post_id: int, text: str):
        if not post_id or not text:
            raise ValueError('Post ID and text are required to reply to a post')
        post: db.Posts = db.Posts.objects(id=post_id).first()
        if not post:
            raise ValueError('Post not found')
        root_post = post.root or post
        parent_ref = models.ComAtprotoRepoStrongRef.Main(cid=post.cid, uri=post.uri)
        root_ref = models.ComAtprotoRepoStrongRef.Main(cid=root_post.cid, uri=root_post.uri)

        reply_post = self.client.send_post(text, reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref))
        db.Posts(text=text, cid=reply_post.cid, uri=reply_post.uri, parent=post, root=root_post).save()