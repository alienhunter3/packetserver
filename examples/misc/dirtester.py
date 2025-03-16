"""Example file for using a directory test server to test without a TNC or radio."""

import msgpack

from packetserver.common import Request, Response, Message
from packetserver.common.testing import DirectoryTestServerConnection, SimpleDirectoryConnection
from packetserver.server.testserver import DirectoryTestServer
from packetserver.server.objects import Object
from packetserver.server.messages import Message as Mail
from packetserver.server.messages import Attachment
import time
import logging
import json
import os
import os.path
from shutil import rmtree

logging.basicConfig(level=logging.DEBUG)

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

ts = DirectoryTestServer(server_callsign, connection_directory=os.path.abspath(conn_dir),
                         data_dir=os.path.abspath(data_dir), zeo=True)
ts.start()

time.sleep(1)
print("creating connection")
new_conn_dir = os.path.join(conn_dir,f"{client_callsign}--{server_callsign}")
os.mkdir(new_conn_dir)

conn = SimpleDirectoryConnection.create_directory_connection(client_callsign, new_conn_dir)
print(conn.remote_callsign)
print(conn.call_to)
print(conn.call_from)

req = Request.blank()

#req.set_var('fetch_attachments', 1)
req.path = ""
req.method = Request.Method.GET

#req.method=Request.Method.POST
#attach = [Attachment("test.txt", "Hello sir, I hope that this message finds you well. The other day..")]
#req.payload = Mail("Hi there from a test user!", "KQ4PEC", attachments=attach).to_dict()


#req.payload = Object(name="test.txt", data="hello there").to_dict()

print("sending request")
conn.send_data(req.pack())
print("Waiting on response.")

data = None
while data is None:
    conn.check_for_data()
    try:
        data = conn.data.unpack()
    except msgpack.OutOfData:
        pass
    time.sleep(.5)

ts.stop()
print("Waiting for server to stop.")
time.sleep(2)
#print(f"Got some data: {data}")
msg = data
print(f"msg: {msg}")
response = Response(Message.partial_unpack(msg))
#print(type(response.payload))
#print(f"Response: {response}: {response.payload}")
print(json.dumps(response.payload, indent=4))
