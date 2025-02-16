import datetime

from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
from uuid import UUID, uuid4
import os.path

class UserWrapper:
    def __init__(self, data: dict):
        self.data = data

def get_user_by_username(client: Client, bbs_callsign: str, username: str)  -> UserWrapper:
    req = Request.blank()
    req.path = "user"
    req.set_var('username', username.strip().upper())
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET user {username} failed: {response.status_code}: {response.payload}")
    return UserWrapper(response.payload)