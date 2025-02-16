import datetime

from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
from uuid import UUID, uuid4
import os.path

class UserWrapper:

    def __init__(self, data: dict):
        for i in ['username', 'status', 'bio', 'socials', 'created_at', 'last_seen', 'email', 'location']:
            if i not in data.keys():
                raise ValueError("Data dict was not an object dictionary.")
        self.data = data

    def __repr__(self):
        return f"<UserWrapper: {self.username}>"

    @property
    def socials(self) -> list[str]:
        return self.data['socials']

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['created_at'])

    @property
    def last_seen(self) -> Optional[datetime.datetime]:
        if self.data['last_seen'] is not None:
            return datetime.datetime.fromisoformat(self.data['last_seen'])
        else:
            return None

    @property
    def username(self) -> str:
        return self.data['username']

    @property
    def status(self) -> str:
        return self.data['status']

    @property
    def bio(self) -> str:
        return self.data['bio']

    @property
    def email(self) -> str:
        return self.data['email']

    @property
    def location(self) -> str:
        return self.data['location']


def get_user_by_username(client: Client, bbs_callsign: str, username: str)  -> UserWrapper:
    req = Request.blank()
    req.path = "user"
    req.set_var('username', username.strip().upper())
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET user {username} failed: {response.status_code}: {response.payload}")
    return UserWrapper(response.payload)

def get_users(client: Client, bbs_callsign: str, limit=None):
    req = Request.blank()
    req.path = "user"
    if limit is not None:
        req.set_var('limit', limit)
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET userlist failed: {response.status_code}: {response.payload}")
    user_list = []
    for u in response.payload:
        user_list.append(UserWrapper(u))
    return user_list