from mongoengine import connect, Document, StringField
import os

connect(os.getenv('TELEGRAM_DATABASE'), host=os.getenv('MONGO_HOST'), port=int(os.getenv('MONGO_PORT')))

class Config(Document):
    Key  = StringField()
    Value = StringField()