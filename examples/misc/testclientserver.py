"""Example file for using a directory test server to test without a TNC or radio."""

import msgpack

from packetserver.common import Request, Response, Message
from packetserver.common.testing import DirectoryTestServerConnection, SimpleDirectoryConnection
from packetserver.server.testserver import DirectoryTestServer
from packetserver.client.testing import TestClient
from packetserver.server.objects import Object
from packetserver.server.messages import Message as Mail
from packetserver.server.messages import Attachment
import time
import logging
import json
import os
import os.path
from shutil import rmtree

#logging.basicConfig(level=logging.DEBUG)

server_callsign = "KQ4PEC"
client_callsign = 'KQ4PEC-7'
#client_callsign = "TEST1"
conn_dir = "/tmp/ts_conn_dir"
data_dir = "/tmp/tmp_ps_data"

if os.path.isdir(conn_dir):
    rmtree(conn_dir)
    os.mkdir(conn_dir)
else:
    os.mkdir(conn_dir)

if not os.path.isdir(data_dir):
    os.mkdir(data_dir)
tc = TestClient(os.path.abspath(conn_dir), client_callsign)
ts = DirectoryTestServer(server_callsign, connection_directory=os.path.abspath(conn_dir),
                         data_dir=os.path.abspath(data_dir), zeo=True)
ts.start()
tc.start()

print("creating connection")
conn = tc.connection_for(server_callsign)

print(conn.remote_callsign)
print(conn.call_to)
print(conn.call_from)
time.sleep(1)
req = Request.blank()

#req.set_var('fetch_attachments', 1)
req.path = ""
req.method = Request.Method.GET

#req.method=Request.Method.POST
#attach = [Attachment("test.txt", "Hello sir, I hope that this message finds you well. The other day..")]
#req.payload = Mail("Hi there from a test user!", "KQ4PEC", attachments=attach).to_dict()


#req.payload = Object(name="test.txt", data="hello there").to_dict()

print("sending request")
resp = tc.send_receive_callsign(req, server_callsign)
ts.stop()
print("Waiting for server to stop.")
time.sleep(1)
response = resp
#print(type(response.payload))
#print(f"Response: {response}: {response.payload}")
print(json.dumps(response.payload, indent=4))
