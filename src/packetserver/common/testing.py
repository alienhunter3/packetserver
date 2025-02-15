from . import PacketServerConnection
from msgpack import Unpacker
from msgpack import packb, unpackb
from pe.connect import Connection, ConnectionState
import logging
from typing import Union

class DummyPacketServerConnection(PacketServerConnection):

    def __init__(self, call_from: str, call_to: str, incoming=False):
        super().__init__(0, call_from, call_to, incoming=incoming)
        self.sent_data = Unpacker()
        self._state = ConnectionState.CONNECTED

    @property
    def state(self):
        return self._state

    def send_data(self, data: Union[bytes, bytearray]):
        self.sent_data.feed(data)
        logging.debug(f"Sender added {data} to self.sent_data.feed")