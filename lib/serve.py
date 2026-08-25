#!/usr/bin/env python3
"""Loopback static server for the app.

Exists instead of `python3 -m http.server` for two reasons: the app must be
served over http rather than file:// (a null origin breaks embedded YouTube
with error 153, and partitions localStorage), and apps grow /api endpoints
that the browser cannot reach cross-origin.

    python3 serve.py <port> <share-dir>
"""
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

MARK = "omacar-server"


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/.mark"):
            body = MARK.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # Add /api/* endpoints here.
        return SimpleHTTPRequestHandler.do_GET(self)


if __name__ == "__main__":
    port, root = int(sys.argv[1]), sys.argv[2]
    import os
    os.chdir(root)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
