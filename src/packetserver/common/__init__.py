from pe.connect import Connection
from threading import Lock
from msgpack import Unpacker


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

