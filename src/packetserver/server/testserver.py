import tempfile
from packetserver.common import (Response, Message, Request, send_response, send_blank_response,
                                 DummyPacketServerConnection)
from shutil import rmtree
from threading import Thread
from . import Server

class TestServer(Server):
    def __init__(self, server_callsign: str, data_dir: str = None, zeo: bool = True):
        super().__init__('localhost', 8000, server_callsign, data_dir=data_dir, zeo=zeo)
        self._data_pid = 1
        self._file_traffic_dir = tempfile.mkdtemp()
        self._file_traffic_thread = None

    def start(self):
        if self.orchestrator is not None:
            self.orchestrator.start()
        self.start_db()
        self.started = True
        self.worker_thread = Thread(target=self.run_worker)
        self.worker_thread.start()

    def stop(self):
        self.started = False
        if self.orchestrator is not None:
            self.orchestrator.stop()
        self.stop_db()
        rmtree(self._file_traffic_dir)

    def data_pid(self) -> int:
        old = self._data_pid
        self._data_pid = self._data_pid + 1
        return old

    def send_test_data(self, conn: DummyPacketServerConnection, data: bytearray):
        conn.data_received(self.data_pid(), data)
        self.server_receiver(conn)
