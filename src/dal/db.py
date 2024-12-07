from mongoengine import connect, Document, StringField, ReferenceField, SequenceField
import os

connect(os.getenv('TELEGRAM_DATABASE'), host=os.getenv('MONGO_HOST'), port=int(os.getenv('MONGO_PORT')))

class Config(Document):
    Key  = StringField()
    Value = StringField()

class Posts(Document):
    id = SequenceField(primary_key=True)
    text = StringField()
    cid = StringField()
    uri = StringField()
    #refs to other Posts
    parent = ReferenceField('self')
    root = ReferenceField('self')