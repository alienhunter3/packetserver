"""BBS private message system"""
import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
import ZODB
import logging
import uuid
from uuid import UUID
from packetserver.common.util import email_valid

# TODO all messages

class Attachment:
    """Name and data that is sent with a message."""
    def __init__(self, name: str, ):
        pass