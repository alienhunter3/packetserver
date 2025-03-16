import tempfile
from packetserver.common import Response, Message, Request, send_response, send_blank_response
from packetserver.common.testing import DirectoryTestServerConnection, DummyPacketServerConnection
from pe.connect import ConnectionState
from shutil import rmtree
from threading import Thread
from . import Server
import os
import os.path
import time
import logging
from traceback import format_exc

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


class DirectoryTestServer(Server):
    def __init__(self, server_callsign: str, connection_directory: str, data_dir: str = None, zeo: bool = True):
        super().__init__('localhost', 8000, server_callsign, data_dir=data_dir, zeo=zeo)
        if not os.path.isdir(connection_directory):
            raise NotADirectoryError(f"{connection_directory} is not a directory or doesn't exist.")
        self._file_traffic_dir = os.path.abspath(connection_directory)
        self._dir_connections = []

    def check_connection_directories(self):
        logging.debug(f"Server checking connection directory {self._file_traffic_dir}")
        if not os.path.isdir(self._file_traffic_dir):
            raise NotADirectoryError(f"{self._file_traffic_dir} is not a directory or doesn't exist.")

        for path in os.listdir(self._file_traffic_dir):
            dir_path = os.path.join(self._file_traffic_dir, path)
            logging.debug(f"Checking directory {dir_path}")
            if not os.path.isdir(dir_path):
                logging.debug(f"Server: {dir_path} is not a directory; skipping")
                continue

            conn_exists = False
            for conn in self._dir_connections:
                if os.path.abspath(conn.directory) == dir_path:
                    conn_exists = True
                    break

            if conn_exists:
                continue

            try:
                conn = DirectoryTestServerConnection.create_directory_connection(self.callsign, dir_path)
                logging.debug(f"New connection detected from {conn.remote_callsign}")
                self._dir_connections.append(conn)
                self.server_connection_bouncer(conn)
            except ValueError:
                logging.debug(format_exc())
                pass

        closed = []

        for conn in self._dir_connections:
            conn.check_for_data()
            if conn.state is not ConnectionState.CONNECTED:
                closed.append(conn)

        for conn in closed:
            if conn in self._dir_connections:
                self._dir_connections.remove(conn)

    def dir_worker(self):
        """Intended to be running as a thread."""
        logging.info("Starting worker thread.")
        while self.started:
            self.server_worker()
            self.check_connection_directories()
            time.sleep(.5)

    def start(self):
        if self.orchestrator is not None:
            self.orchestrator.start()
        self.start_db()
        self.started = True
        self.worker_thread = Thread(target=self.dir_worker)
        self.worker_thread.start()

    def stop(self):
        self.started = False
        if self.orchestrator is not None:
            self.orchestrator.stop()
        self.stop_db()
