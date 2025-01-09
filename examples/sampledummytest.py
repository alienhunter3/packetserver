"""This is just an example of how to use the DummyPacketServerConnection and TestServer classes without a radio."""
from packetserver.common import DummyPacketServerConnection, Request, Response, Message
from packetserver.server import TestServer
import time
import logging

logging.basicConfig(level=logging.DEBUG)

server_callsign = "KQ4PEC"
client_callsign = 'KQ4PEC-7'
ts = TestServer(server_callsign, zeo=True)
ts.start()

time.sleep(1)
print("creating connection")

conn = DummyPacketServerConnection(client_callsign, server_callsign, incoming=True)
print(conn.remote_callsign)
print(conn.call_to)
print(conn.call_from)
conn.connected()

req = Request.blank()
req.path = "user"
req.method=Request.Method.GET
print("sending request")
conn.data_received(0, bytearray(req.pack()))
#ts.send_test_data(conn, bytearray(req.pack()))
print("Waiting on response.")
time.sleep(.5)
ts.stop()
msg = conn.sent_data.unpack()
print(f"msg: {msg}")
response = Response(Message.partial_unpack(msg))
print(f"Response: {response}: {response.payload}")
