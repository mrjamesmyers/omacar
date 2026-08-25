#!/usr/bin/env python3
"""Loopback server for the OmaCar cluster.

Serves share/ over http (never file:// — a null origin partitions
localStorage and breaks fetch against our own /api), and exposes the
snapshot the daemon publishes.

    /api/live            the current sample
    /api/history?n=300   recent rows from telemetry.db

Deliberately does no OBD work of its own. One process owns the serial
connection, and it is the daemon.

    python3 serve.py <port> <share-dir>
"""
import json
import os
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

MARK = "omacar-server"
STATE = os.path.expanduser(
    os.environ.get("XDG_STATE_HOME", "~/.local/state") + "/omacar")
LIVE = os.path.join(STATE, "live.json")
DB = os.path.join(STATE, "telemetry.db")

HISTORY_COLS = ["t", "rpm", "speed", "load", "throttle", "coolant", "intake",
                "maf", "stft", "ltft", "timing", "lphk", "eff"]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _live(self):
        try:
            with open(LIVE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"connected": False, "status": "no daemon"}

    def _history(self, n):
        if not os.path.exists(DB):
            return []
        try:
            db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            rows = db.execute(
                f"SELECT {','.join(HISTORY_COLS)} FROM samples "
                "ORDER BY t DESC LIMIT ?", (n,)).fetchall()
            db.close()
        except sqlite3.Error:
            return []
        return [dict(zip(HISTORY_COLS, r)) for r in reversed(rows)]

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""

        if path == "/.mark":
            return self._send(MARK.encode(), "text/plain")
        if path == "/api/live":
            return self._send(json.dumps(self._live()).encode())
        if path == "/api/history":
            n = 300
            for part in query.split("&"):
                if part.startswith("n="):
                    try:
                        n = max(1, min(5000, int(part[2:])))
                    except ValueError:
                        pass
            return self._send(json.dumps(self._history(n)).encode())
        return SimpleHTTPRequestHandler.do_GET(self)


if __name__ == "__main__":
    port, root = int(sys.argv[1]), sys.argv[2]
    os.chdir(root)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
