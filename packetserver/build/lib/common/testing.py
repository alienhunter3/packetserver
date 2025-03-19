import msgpack

from . import PacketServerConnection
from pe.connect import ConnectionState
from msgpack import Unpacker
from typing import Union, Self, Optional
import os.path
import logging
import ax25

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

class DirectoryTestServerConnection(PacketServerConnection):
    """Monitors a directory for messages in msgpack format."""
    def __init__(self, call_from: str, call_to: str, directory: str, incoming=False):
        super().__init__(0, call_from, call_to, incoming=incoming)
        self._state = ConnectionState.CONNECTED
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"No such directory as {directory}")
        self._directory = directory
        self._sent_data = Unpacker()
        self._pid = 1
        self.closing = False

    @classmethod
    def create_directory_connection(cls, self_callsign: str, directory: str) -> Self:

        if not ax25.Address.valid_call(self_callsign):
            raise ValueError("self_callsign must be a valid callsign.")

        if not os.path.isdir(directory):
            raise NotADirectoryError(f"{directory} is not a directory or doesn't exist.")

        spl = os.path.basename(directory).split('--')
        if len(spl) != 2:
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        src = spl[0]
        dst = spl[1]

        if not ax25.Address.valid_call(src):
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        if not ax25.Address.valid_call(dst):
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        if dst.upper() == self_callsign.upper():
            incoming = True
        else:
            incoming = False

        return DirectoryTestServerConnection(src, dst, directory, incoming=incoming)

    @property
    def pid(self) -> int:
        old = self._pid
        self._pid = self._pid + 1
        return old

    @property
    def directory(self) -> str:
        return self._directory

    @property
    def state(self):
        return self._state

    @property
    def file_path(self) -> str:
        file_name = f"{self.local_callsign}.msg"
        file_path = os.path.join(self._directory, file_name)
        return file_path

    @property
    def remote_file_path(self) -> str:
        file_name = f"{self.remote_callsign}.msg"
        file_path = os.path.join(self._directory, file_name)
        return file_path

    def check_closed(self):
        if self.closing:
            self._state = ConnectionState.DISCONNECTED
        if self._state is not ConnectionState.CONNECTED:
            return True
        if not os.path.isdir(self._directory):
            self._state = ConnectionState.DISCONNECTED
            self.disconnected()
            return True
        return False

    def write_out(self, data: bytes):
        if self.check_closed():
            raise RuntimeError("Connection is closed. Cannot send.")

        if os.path.exists(self.file_path):
            raise RuntimeError("The outgoing message file already exists. State is wrong for sending.")

        if os.path.exists(self.file_path+".tmp"):
            os.remove(self.file_path+".tmp")

        open(self.file_path+".tmp", 'wb').write(data)
        os.rename(self.file_path+".tmp", self.file_path)

    def send_data(self, data: Union[bytes, bytearray]):
        if self.check_closed():
            raise RuntimeError("Connection is closed. Cannot send.")
        self._sent_data.feed(data)
        logging.debug(f"Sender added {data} to self.sent_data.feed")
        try:
            obj = self._sent_data.unpack()
            self.write_out(msgpack.packb(obj))
            logging.debug(f"Wrote complete binary message to {self.file_path}")
        except msgpack.OutOfData as e:
            pass

    def check_for_data(self):
        """Monitors connection directory for data."""
        if self.closing:
            self._state = ConnectionState.DISCONNECTED
        if self.check_closed():
            return

        if os.path.isfile(self.remote_file_path):
            logging.debug(f"{self.local_callsign} Found that the remote file path '{self.remote_file_path}' exists now.")
            data = open(self.remote_file_path, 'rb').read()
            self.data_received(self.pid, bytearray(data))
            os.remove(self.remote_file_path)
            logging.debug(f"{self.local_callsign} detected data from {self.remote_callsign}: {msgpack.unpackb(data)}")


class SimpleDirectoryConnection:
    def __init__(self, call_from: str, call_to: str, directory: str, incoming=False):
        self._state = ConnectionState.CONNECTED
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"No such directory as {directory}")
        self._directory = directory
        self._sent_data = Unpacker()
        self.data = Unpacker()
        self._pid = 1
        self.call_to = call_to
        self.call_from = call_from
        self.incoming = incoming
        self._incoming = incoming
        self.closing = False
        if incoming:
            self.local_callsign = call_to
            self.remote_callsign = call_from
        else:
            self.local_callsign = call_from
            self.remote_callsign = call_to

    @classmethod
    def create_directory_connection(cls, self_callsign: str, directory: str) -> Self:

        if not ax25.Address.valid_call(self_callsign):
            raise ValueError("self_callsign must be a valid callsign.")

        if not os.path.isdir(directory):
            raise NotADirectoryError(f"{directory} is not a directory or doesn't exist.")

        spl = os.path.basename(directory).split('--')
        if len(spl) != 2:
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        src = spl[0]
        dst = spl[1]

        if not ax25.Address.valid_call(src):
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        if not ax25.Address.valid_call(dst):
            raise ValueError(f"Directory {directory} has the wrong name to be a connection dir.")

        if dst.upper() == self_callsign.upper():
            incoming = True
        else:
            incoming = False

        return SimpleDirectoryConnection(src, dst, directory, incoming=incoming)

    @property
    def pid(self) -> int:
        old = self._pid
        self._pid = self._pid + 1
        return old

    @property
    def directory(self) -> str:
        return self._directory

    @property
    def state(self):
        return self._state

    @property
    def file_path(self) -> str:
        file_name = f"{self.local_callsign}.msg"
        file_path = os.path.join(self._directory, file_name)
        return file_path

    @property
    def remote_file_path(self) -> str:
        file_name = f"{self.remote_callsign}.msg"
        file_path = os.path.join(self._directory, file_name)
        return file_path

    def check_closed(self):
        if self.closing:
            self._state = ConnectionState.DISCONNECTED
        if self._state is not ConnectionState.CONNECTED:
            return True
        if not os.path.isdir(self._directory):
            self._state = ConnectionState.DISCONNECTED
            return True
        return False

    def write_out(self, data: bytes):
        if self.check_closed():
            raise RuntimeError("[SIMPLE] Connection is closed. Cannot send.")

        if os.path.exists(self.file_path):
            raise RuntimeError("[SIMPLE] The outgoing message file already exists. State is wrong for sending.")

        if os.path.exists(self.file_path+".tmp"):
            os.remove(self.file_path+".tmp")

        open(self.file_path+".tmp", 'wb').write(data)
        os.rename(self.file_path+".tmp", self.file_path)

    def send_data(self, data: Union[bytes, bytearray]):
        if self.check_closed():
            raise RuntimeError("[SIMPLE] Connection is closed. Cannot send.")
        self._sent_data.feed(data)
        logging.debug(f"[SIMPLE] Sender added {data} to self.sent_data.feed")
        try:
            obj = self._sent_data.unpack()
            self.write_out(msgpack.packb(obj))
            logging.debug(f"[SIMPLE] Wrote complete binary message to {self.file_path}")
        except msgpack.OutOfData as e:
            pass

    def check_for_data(self) -> bool:
        """Monitors connection directory for data."""
        if self.closing:
            self._state = ConnectionState.DISCONNECTED
        if self.check_closed():
            return False
        if os.path.isfile(self.remote_file_path):
            data = open(self.remote_file_path, 'rb').read()
            os.remove(self.remote_file_path)
            logging.debug(f"[SIMPLE] {self.local_callsign} detected data from {self.remote_callsign}: {data}")
            self.data.feed(data)
            return True
        else:
            return False
