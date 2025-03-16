"""Example file for using a directory test server to test without a TNC or radio."""

from packetserver.server.testserver import DirectoryTestServer
import os.path
from shutil import rmtree
import logging

logging.basicConfig(level=logging.DEBUG)

server_callsign = "KQ4PEC"
conn_dir = "/tmp/ts_conn_dir"
data_dir = "/tmp/tmp_ps_data"

if os.path.isdir(conn_dir):
    rmtree(conn_dir)
    os.mkdir(conn_dir)
else:
    os.mkdir(conn_dir)

if not os.path.isdir(data_dir):
    os.mkdir(data_dir)
ts = DirectoryTestServer(server_callsign, connection_directory=os.path.abspath(conn_dir),
                         data_dir=os.path.abspath(data_dir), zeo=True)
ts.start()