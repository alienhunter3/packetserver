#!/usr/bin/env python3
"""
PacketServer HTTP Server Runner

Standalone runner with --db support (local FileStorage or ZEO).

Examples:
  python packetserver/runners/http_server.py --db /path/to/Data.fs --port 8080
  python packetserver/runners/http_server.py --db zeo.host.com:8100
"""

import argparse
import sys

import uvicorn
from packetserver.http.server import app

def main():
    parser = argparse.ArgumentParser(description="Run the PacketServer HTTP API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload during development")

    args = parser.parse_args()

    uvicorn.run(
        "packetserver.http.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

if __name__ == "__main__":
    main()