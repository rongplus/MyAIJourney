# -*- coding: utf-8 -*-
import pika
from pika import Exchange, DeliveryMethod
from pika.adapters import mq_url
from pika.core import NoSuchExchange, NoSuchBinding, NoSuchChannel, BadChannelClosed

from .models import Message

def send_to_queue(message):
    credentials = pika.Credentials()
    host = 'localhost'
    exchange = Exchange()
    channel = pika.Channel()
    try:
        connection = pika.BlockingConnection(
            mq_url.MQURL(host=host, exchange=exchange, credentials=credentials))
        channel = connection.channel()
        channel.send(message)
    except (NoSuchExchange, NoSuchBinding, NoSuchChannel, BadChannelClosed):
        raise

def get_from_queue():
    credentials = pika.Credentials()
    host = 'localhost'
    exchange = Exchange()
    channel = pika.Channel()
    try:
        connection = pika.BlockingConnection(
            mq_url.MQURL(host=host, exchange=exchange, credentials=credentials))
        channel = connection.channel()
        result = channel.get_result()
        return result.body
    except (NoSuchExchange, NoSuchBinding, NoSuchChannel, BadChannelClosed):
        return None

def clear_queue():
    credentials = pika.Credentials()
    host = 'localhost'
    exchange = Exchange()
    channel = pika.Channel()
    try:
        connection = pika.BlockingConnection(
            mq_url.MQURL(host=host, exchange=exchange, credentials=credentials))
        channel = connection.channel()
        channel.cancel()
    except (NoSuchExchange, NoSuchBinding, NoSuchChannel, BadChannelClosed):
        pass
