import pika
import json
from api.bsky_api import handle_event, Event

import os

rabbit_user = os.environ.get('RABBIT_USER')
rabbit_password = os.environ.get('RABBIT_PASSWORD')

def callback(ch, method, properties, body):
    try:
        event =  Event(**json.loads(body))
        handle_event(event)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f'Error handling event: {e}')
        ch.basic_ack(delivery_tag=method.delivery_tag) # so it doesn't get stuck in the queue

def main():
    credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
    connection = pika.BlockingConnection(pika.ConnectionParameters('orange-rabbit', credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue='bsky_update_queue')

    channel.basic_consume(queue='bsky_update_queue', on_message_callback=callback)

    print('Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == '__main__':
    main()