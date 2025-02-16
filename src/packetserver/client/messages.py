import datetime

from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
from uuid import UUID, uuid4
import os.path

# TODO messages client

class MessageWrapper:
    # TODO MessageWrapper
    def __init__(self, data: dict):
        for i in ['username', 'status', 'bio', 'socials', 'created_at', 'last_seen', 'email', 'location']:
            if i not in data.keys():
                raise ValueError("Data dict was not an object dictionary.")
        self.data = data


def send_message(client: Client, bbs_callsign: str,):
    # TODO send message
    pass

def get_message_uuid():
    # TODO get message by uuid
    pass

def get_messages_since():
    # TODO get messages since date
    pass

def get_messages():
    # TODO get messages default
    pass