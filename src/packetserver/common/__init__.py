from pe.connect import Connection
from threading import Lock
from msgpack import Unpacker
from msgpack import packb, unpackb
from enum import Enum
import bz2
from typing import Union, Self


class PacketServerConnection(Connection):

    connection_subscribers = []
    receive_subscribers = []

    def __init__(self, port, call_from, call_to, incoming=False):
        super().__init__(port, call_from, call_to, incoming=incoming)
        # Now perform any initialization of your own that you might need
        self.data = Unpacker()
        self.data_lock = Lock()

    def connected(self):
        print("connected")
        for fn in PacketServerConnection.connection_subscribers:
            fn(self)

    def disconnected(self):
        pass

    def data_received(self, pid, data):
        with self.data_lock:
            self.data.feed(data)
        for fn in PacketServerConnection.receive_subscribers:
            fn(self)

    @classmethod
    def query_accept(cls, port, call_from, call_to):
        return True


class Message:
    """Base class for communication encapsulated in msgpack objects."""

    class CompressionType(Enum):
        NONE = 0
        BZIP2 = 1
        GZIP = 2
        DEFLATE = 3

    class MessageType(Enum):
        REQUEST = 0
        RESPONSE = 1

    def __init__(self, msg_type: MessageType, compression: CompressionType,  payload: dict):
        self.type = Message.MessageType(msg_type)
        self.compression = Message.CompressionType(compression)
        self.data = payload

    @property
    def vars(self) -> dict:
        if 'v' in self.data:
            if type(self.data['v']) is dict:
                return self.data['v']
        return {}

    def get_var(self, key: str):
        if 'v' not in self.data:
            raise KeyError(f"Variable '{key}' not found.")
        if str(key) not in self.data['v']:
            raise KeyError(f"Variable '{key}' not found.")
        return self.data['v'][str(key)]

    def set_var(self, key: str, value):
        if 'v' not in self.data:
            self.data['v'] = {}
        self.data['v'][str(key)] = value

    @property
    def data_bytes(self):
        return packb(self.data)

    def pack(self) -> bytes:
        output = {'t': self.type.value, 'c': self.compression.value}
        data_bytes = self.data_bytes

        if (self.compression is self.CompressionType.NONE) or (len(data_bytes) < 30):
            output['d'] = data_bytes
            return packb(output)

        if self.compression is self.CompressionType.BZIP2:
            compressed = bz2.compress(packb(self.data))
        else:
            raise NotImplementedError(f"Compression type {self.compression.name} is not implemented yet.")

        if len(compressed) < len(data_bytes):
            output['d'] = compressed
        else:
            output['d'] = data_bytes
            output['c'] = self.CompressionType.NONE.value
        return packb(output)

    @property
    def payload(self):
        if 'd' in self.data:
            pl = self.data['d']
            if type(pl) in (dict, str, bytes):
                return pl
            else:
                return str(pl)
        else:
            return ""

    @payload.setter
    def payload(self, payload: Union[str, bytes, dict]):
        if type(payload) in (str, bytes, dict):
            self.data['d'] = payload
        else:
            self.data['d'] = str(payload)

    @classmethod
    def unpack(cls, msg_bytes: bytes) -> Self:
        try:
            unpacked = unpackb(msg_bytes)
        except Exception as e:
            raise ValueError("ERROR: msg_bytes didn't contain a valid msgpack object.\n" + str(e))
        for i in ('t', 'c', 'd'):
            if i not in unpacked:
                raise ValueError("ERROR: unpacked bytes do not contain a valid Message object.")

        comp = Message.CompressionType(unpacked['c'])
        msg_type = Message.MessageType(unpacked['t'])
        raw_data = unpacked['d']

        if comp is Message.CompressionType.NONE:
            data = unpackb(raw_data)
        elif comp is Message.CompressionType.BZIP2:
            data = unpackb(bz2.decompress(raw_data))
        else:
            raise NotImplementedError(f"Compression type {comp.name} is not implemented yet.")
        return Message(msg_type, comp, data)

class Request(Message):
    class Method(Enum):
        GET = 0
        POST = 1
        UPDATE = 2
        DELETE = 3

    def __init__(self, msg: Message):
        if msg.type is not Message.MessageType.REQUEST:
            raise ValueError(f"Can't create a Request Object from a {msg.type} Message object.")

        super().__init__(msg.type, msg.compression, msg.data)

        if ('p' in msg.data) and (type(msg.data['p']) is not str):
            raise ValueError("Path of Request must be a string.")

        if 'm' in msg.data:
            if type(msg.data['m']) is not bytes:
                raise ValueError("Method of Request must be bytes.")
            self.Method(int(self.data['m'][0]))

    @property
    def path(self):
        if 'p' in self.data:
            return str(self.data['p'])
        else:
            return ""

    @path.setter
    def path(self, path: str):
        self.data['p'] = str(path.strip())

    @property
    def method(self) -> Method:
        if 'm' in self.data:
            return self.Method(int(self.data['m'][0]))
        else:
            return self.Method.GET

    @method.setter
    def method(self, meth: Method):
        meth = self.Method(meth)
        self.data['m'] = meth.value.to_bytes(1)

    @classmethod
    def unpack(cls, msg_bytes: bytes) -> Self:
        msg = super().unpack(msg_bytes)
        return Request(msg)

    @classmethod
    def blank(cls) -> Self:
        msg = Message(Message.MessageType.REQUEST, Message.CompressionType.NONE, {})
        return Request(msg)

    def __repr__(self):
        return f"<Request: {self.method.name} '{self.path}'>"

class Response(Message):
    def __init__(self, msg: Message):
        if msg.type is not Message.MessageType.RESPONSE:
            raise ValueError(f"Can't create a Response Object from a {msg.type} Message object.")

        super().__init__(msg.type, msg.compression, msg.data)
        if 'c' in msg.data:
            status_bytes = self.data['c']
            if type(status_bytes) is not bytes:
                raise ValueError("Invalid Response data")
            status_code = int.from_bytes(status_bytes)
            if status_code >= 600:
                raise ValueError("Invalid status code.")

    @classmethod
    def unpack(cls, msg_bytes: bytes) -> Self:
        msg = super().unpack(msg_bytes)
        return Response(msg)

    @classmethod
    def blank(cls) -> Self:
        msg = Message(Message.MessageType.RESPONSE, Message.CompressionType.NONE, {})
        return Response(msg)

    @property
    def status_code(self) -> int:
        if 'c' in self.data:
            status_bytes = self.data['c']
            if type(status_bytes) is not bytes:
                raise ValueError("Invalid Response data")
            status_code = int.from_bytes(status_bytes)
            if status_code >= 600:
                raise ValueError("Invalid status code.")
            return status_code
        else:
            return 200

    @status_code.setter
    def status_code(self, code: int):
        if (code <= 0) or (code >= 600):
            raise ValueError("Status must be a positive integer <= 600")
        self.data['c'] = code.to_bytes(2)

    def __repr__(self):
        return f"<Response: {self.status_code}>"