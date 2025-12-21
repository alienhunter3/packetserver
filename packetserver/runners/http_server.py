# runners/http_server.py
import uvicorn
from packetserver.http.server import app
from packetserver.database import open_db  # adjust to your actual DB opener

# Ensure DB is open (same as main server)
open_db()  # or however you initialize the global DB connection

if __name__ == "__main__":
    uvicorn.run(
        "packetserver.http.server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,  # convenient during development
    )