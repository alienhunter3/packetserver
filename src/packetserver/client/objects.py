import datetime

from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
from uuid import UUID, uuid4
import os.path



class ObjectWrapper:
    def __init__(self, data: dict):
        for i in ['name', 'uuid_bytes', 'binary', 'private', 'created_at', 'modified_at', 'data']:
            if i not in data.keys():
                raise ValueError("Data dict was not an object dictionary.")
        self.obj_data = data

    @property
    def size(self) -> int:
        return len(self.obj_data['data'])

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.obj_data['created_at'])

    @property
    def modified(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.obj_data['modified_at'])

    @property
    def uuid(self) -> UUID:
        return UUID(bytes=self.obj_data['uuid_bytes'])

    @property
    def private(self) -> bool:
        return self.obj_data['private']

    @property
    def binary(self) -> bool:
        return self.obj_data['binary']

    @property
    def data(self) -> Union[str, bytes]:
        if self.binary:
            return self.obj_data['data']
        else:
            return self.obj_data['data'].decode()


def post_object(client: Client, bbs_callsign: str, name:str, data: Union[str, bytes, bytearray], private=True) -> UUID:
    if type(data) in [bytes, bytearray]:
        data = bytes(data)
        binary = True
    else:
        binary = False
        data = str(data).encode()

    req = Request.blank()
    req.path = "object"
    req.payload = {'name': name, 'data': data, 'binary': binary, 'private': private}
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"Posting object failed: {response.status_code}: {response.payload}")
    return UUID(response.payload)

def post_file(client: Client, bbs_callsign: str, file_path: str, private=True, name: str = None, binary=True) -> UUID:
    if name is None:
        obj_name = os.path.basename(file_path)
    else:
        obj_name = os.path.basename(str(name))
    if binary:
        mode = 'rb'
    else:
        mode = 'r'
    data = open(file_path, mode).read()
    return post_object(client, bbs_callsign, obj_name, data, private=private)

def get_object_by_uuid(client: Client, bbs_callsign: str, uuid: Union[str, bytes, UUID, int]):
    if type(uuid) is str:
        uid = UUID(uuid)
    elif type(uuid) is bytes:
        uid = UUID(bytes=uuid)
    elif type(uuid) is UUID:
        uid = uuid
    elif type(uuid) is int:
        uid = UUID(int=uuid)
    else:
        raise ValueError("uuid must represent a UUID object")

    req = Request.blank()
    req.path = "object"
    req.set_var('uuid', uid.bytes)
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return ObjectWrapper(response.payload)

