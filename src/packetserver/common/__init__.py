from pe.connect import Connection
from threading import Lock
from msgpack import Unpacker
from msgpack import packb, unpackb
from enum import Enum
import bz2
from typing import Union, Self
import datetime
import logging
import ax25


class PacketServerConnection(Connection):

    connection_subscribers = []
    receive_subscribers = []
    max_send_size = 2000

    def __init__(self, port, call_from, call_to, incoming=False):
        super().__init__(port, call_from, call_to, incoming=incoming)
        # Now perform any initialization of your own that you might need
        self.data = Unpacker()
        self.data_lock = Lock()
        self.connection_created = datetime.datetime.now(datetime.UTC)
        self.connection_last_activity = datetime.datetime.now(datetime.UTC)
        self.closing = False


    @property
    def local_callsign(self):
        if self.incoming:
            return self.call_to
        else:
            return self.call_from

    @property
    def remote_callsign(self):
        if self.incoming:
            return self.call_from
        else:
            return self.call_to

    def connected(self):
        print("connected")
        logging.debug(f"new connection from {self.call_from} to {self.call_to}")
        for fn in PacketServerConnection.connection_subscribers:
            fn(self)

    def disconnected(self):
        logging.debug(f"connection disconnected: {self.call_from} -> {self.call_to}")

    def data_received(self, pid, data):
        self.connection_last_activity = datetime.datetime.now(datetime.UTC)
        logging.debug(f"received data: {data}")
        with self.data_lock:
            logging.debug(f"fed received data to unpacker {data}")
            self.data.feed(data)
        for fn in PacketServerConnection.receive_subscribers:
            logging.debug("found function to notify about received data")
            fn(self)
            logging.debug("notified function about received data")

    def send_data(self, data: Union[bytes, bytearray]):
        logging.debug(f"sending data: {data}")
        self.connection_last_activity = datetime.datetime.now(datetime.UTC)
        if len(data) > self.max_send_size:
            logging.debug(f"Large frame detected {len(data)} breaking it up into chunks")
            index = 0
            counter = 0
            while index <= len(data):
                logging.debug(f"Sending chunk {counter}")
                if (len(data) - index) < self.max_send_size:
                    super().send_data(data[index:])
                    break
                super().send_data(data[index:index + self.max_send_size])
                index = index + self.max_send_size
                counter = counter + 1
        else:
            super().send_data(data)

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
        logging.debug("Packing Message")
        if (self.compression is self.CompressionType.NONE) or (len(data_bytes) < 30):
            output['d'] = data_bytes
            output['c'] = self.CompressionType.NONE.value
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
    def partial_unpack(cls, msg: dict) -> Self:
        unpacked = msg
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

    @classmethod
    def unpack(cls, msg_bytes: bytes) -> Self:
        try:
            unpacked = unpackb(msg_bytes)
        except Exception as e:
            raise ValueError("ERROR: msg_bytes didn't contain a valid msgpack object.\n" + str(e))
        if type(unpacked) is not dict:
            raise ValueError("ERROR: unpacked message was not a packetserver message.")
        for i in ('t', 'c', 'd'):
            if i not in unpacked:
                raise ValueError("ERROR: unpacked message was not a packetserver message.")
        return Message.partial_unpack(unpacked)

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

        if 'p' in self.data:
            self.data['p'] = str(self.data['p']).strip().lower()

        if 'm' in msg.data:
            if type(msg.data['m']) is not bytes:
                raise ValueError("Method of Request must be bytes.")
            self.Method(int(self.data['m'][0]))

    @property
    def path(self):
        if 'p' in self.data:
            return str(self.data['p']).lower().strip()
        else:
            return ""

    @path.setter
    def path(self, path: str):
        self.data['p'] = str(path).strip().lower()

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

def send_response(conn: PacketServerConnection, response: Response, original_request: Request,
                  compression: Message.CompressionType = Message.CompressionType.BZIP2):
    if conn.state.name == "CONNECTED" and not conn.closing:

        # figure out compression setting based on request
        logging.debug("Determining compression of response")
        comp = compression
        logging.debug(f"Default comp: {comp}")
        logging.debug(f"Original vars: {original_request.vars}")
        if 'C' in original_request.vars:
            logging.debug(f"Detected compression header in original request: {original_request.vars['C']}")
            val = original_request.vars['C']
            for i in Message.CompressionType:
                logging.debug(f"Checking type: {i}")
                if str(val).strip().upper() == i.name:
                    comp = i
                    logging.debug(f"matched compression with var to {comp}")
                    break
                try:
                    if int(val) == i.value:
                        comp = i
                        logging.debug(f"matched compression with var to {comp}")
                except ValueError:
                    pass
        response.compression = comp
        logging.debug(f"Final compression: {response.compression}")

        logging.debug(f"sending response: {response}, {response.compression}, {response.payload}")
        conn.send_data(response.pack())
        logging.debug("response sent successfully")

def send_blank_response(conn: PacketServerConnection, original_request: Request, status_code: int = 200,
                  payload: Union[bytes, bytearray, str, dict] = ""):
    response = Response.blank()
    response.status_code = status_code
    response.payload = payload
    send_response(conn, response, original_request)