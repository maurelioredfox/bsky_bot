from io import BytesIO
import os
import re as regex
from atproto import AtUri, Client, models, IdResolver
from atproto.exceptions import BadRequestError
import base64
from dal import db
from PIL import Image
from typing import Optional

def is_valid_bluesky_url(url: str) -> bool:
    """Check if the given URL is a valid Bluesky post URL.

    Args:
        url (str): URL to check.
    Returns:
        bool: True if the URL is a valid Bluesky post URL, otherwise False.
    """
    bluesky_regex = r'^https?:\/\/bsky\.app\/profile\/[^\/]+\/post\/[^\/]+$'
    return bool(regex.match(bluesky_regex, url))

class BlueskyService():
    def __init__(self):
        self.client = Client()
        self.resolver = IdResolver()
        self.client.login(os.environ['BSKY_USERNAME'], os.environ['BSKY_PASSWORD'])


    def fetch_post(self, url: str) -> Optional[models.ComAtprotoRepoStrongRef.Main]:
        """Fetch a post using its Bluesky URL.

        Args:
            client (Client): Authenticated Atproto client.
            resolver (IdResolver): Resolver instance for DID lookup.
            url (str): URL of the Bluesky post.
        Returns:
            :obj:`models.AppBskyFeedPost.Record`: Post if found, otherwise None.
        """
        try:
            # Extract the handle and post rkey from the URL
            url_parts = url.split('/')
            handle = url_parts[4]  # Username in the URL
            post_rkey = url_parts[6]  # Post Record Key in the URL

            # Resolve the DID for the username
            did = self.resolver.handle.resolve(handle)
            if not did:
                print(f'Could not resolve DID for handle "{handle}".')
                return None

            # Fetch the post record
            return models.create_strong_ref(self.client.get_post(post_rkey, did))
        except (ValueError, KeyError) as e:
            print(f'Error fetching post for URL {url}: {e}')
            return None
    
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
    
    def make_photo_post_content(self, photo, link):
        """Create a post content with photos and an optional link."""
        photos = []
        aspect_ratios = []

        for p in photo:
            photo_data = base64.b64decode(p)
            uploaded_photo = self.client.upload_blob(photo_data).blob
            image: Image = Image.open(BytesIO(photo_data))
            aspect_ratio = models.AppBskyEmbedDefs.AspectRatio(height=image.height, width=image.width)
            aspect_ratios.append(aspect_ratio)
            photos.append(uploaded_photo)
        if link:
            if is_valid_bluesky_url(link):
                # If the link is a Bluesky post, fetch the post details
                post_record = self.fetch_post(link)
                if post_record:
                    embed = models.AppBskyEmbedRecordWithMedia.Main(
                        record=models.AppBskyEmbedRecord.Main(record=post_record),
                        media=models.AppBskyEmbedImages.Main(
                            images=[
                                models.AppBskyEmbedImages.Image(
                                    image=photo,
                                    alt='',  # Optional alt text can be set if needed
                                    aspect_ratio=aspect_ratio
                                ) for photo, aspect_ratio in zip(photos, aspect_ratios)
                            ]
                        )
                    )
            else:
                # If the link is not a Bluesky post, create an embed for the images with the link
                embed = models.AppBskyEmbedImages.Main(
                    images=[models.AppBskyEmbedImages.Image(
                        image=photo,
                        aspect_ratio=aspect_ratio
                    ) for photo, aspect_ratio in zip(photos, aspect_ratios)],
                    external=models.AppBskyEmbedExternal.Main(
                        external=models.AppBskyEmbedExternal.External(
                            uri=link,
                            title=None,  # Optional title can be set if needed
                            description=None  # Optional description can be set if needed
                        )
                    )
                )
        else:
            # If there is no link, create an embed for the images
            embed = models.AppBskyEmbedImages.Main(
                images=[models.AppBskyEmbedImages.Image(
                    image=photo,
                    alt='',  # Optional alt text can be set if needed
                    aspect_ratio=aspect_ratio
                ) for photo, aspect_ratio in zip(photos, aspect_ratios)]
            )

        return embed
        
    def make_link_post_content(self, link: str):
        """Create a post content with a link."""
        if is_valid_bluesky_url(link):
            # If the link is a Bluesky post, fetch the post details
            post_record = self.fetch_post(link)
            if post_record:
                return models.AppBskyEmbedRecord.Main(record=post_record)
        else:
            # If the link is not a Bluesky post, create an embed for the link
            return models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=link,
                    title=None,  # Optional title can be set if needed
                    description=None  # Optional description can be set if needed
                )
            )

    def post(self, text: str, photo = None, link = None):
        if not text and not photo:
            raise ValueError('At least one field must be provided to create a post')
        
        embed = None

        if photo and len(photo) > 0:
            if len(photo) > 4:
                raise ValueError('You can only upload up to 4 photos in a single post')
            embed = self.make_photo_post_content(photo, link)
        elif link:
            embed = self.make_link_post_content(link)

        post = self.client.send_post(text, embed=embed)
        db.Posts(text=text, cid=post.cid, uri=post.uri).save()

    def repost(self, original_post_url: str):
        if not is_valid_bluesky_url(original_post_url):
            raise ValueError('Invalid Bluesky post URL')

        post_record = self.fetch_post(original_post_url)
        if not post_record:
            raise ValueError('Post not found or could not be fetched')

        # Create a repost
        repost = self.client.repost(uri=post_record.uri, cid=post_record.cid)
        db.Posts(text=f'retweet from this: {original_post_url}', cid=repost.cid, uri=repost.uri).save()

    def delete_post(self, post_id: int):
        if not post_id:
            raise ValueError('Post ID is required to delete a post')
        post = db.Posts.objects(id=post_id).first()
        if not post:
            raise ValueError('Post not found')
        self.client.delete_post(post.uri)
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

    def add_to_list(self, username: str):
        """Add a user to the Bluesky list."""
        if not username:
            raise ValueError('Username is required to add to the list')

        # Check if the list exists
        mod_list_uri = os.getenv("BLUESKY_LIST", "")
        if not mod_list_uri:
            raise ValueError('BLUESKY_LIST environment variable is not set')

        # Resolve the DID for the username
        user_to_add = self.resolver.handle.resolve(username)
        if not user_to_add:
            raise ValueError(f'Could not resolve DID for handle "{username}"')

        # Resolve mod list owner
        mod_list_owner = AtUri.from_str(mod_list_uri)

        _ = self.client.app.bsky.graph.listitem.create(
            mod_list_owner,
            models.AppBskyGraphListitem.Record(
                list=mod_list_uri,
                subject=user_to_add,
                created_at=self.client.get_current_time_iso(),
            ),
        )