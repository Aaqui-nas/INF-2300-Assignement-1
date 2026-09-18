#!/usr/bin/env python3
import socketserver
import os
import json
import tempfile
from email.utils import formatdate
from urllib.parse import urlsplit, unquote


"""
Written by: Raymon Skjørten Hansen
Email: raymon.s.hansen@uit.no
Course: INF-2300 - Networking
UiT - The Arctic University of Norway
May 9th, 2019
"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")
SERVER_NAME = "INF2300-HTTPServer/1.0"

HTTP_STATUS_REASONS = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    501: "Not Implemented",
}

CONTENT_TYPES = {
    ".html": "text/html",
    ".txt": "text/plain",
    ".ico": "image/x-icon",
}


class _BadRequest(Exception):
    """Raised while parsing a request that doesn't conform to HTTP/1.1."""


def load_messages():
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as infile:
            data = json.load(infile)
        return data.get("next_id", 1), data.get("messages", [])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 1, []


def save_messages(next_id, messages):
    """Persist state atomically: write to a temp file, then replace in one step
    so a crash mid-write never leaves messages.json half-written."""
    data = {"next_id": next_id, "messages": messages}
    fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file)
        os.replace(tmp_path, MESSAGES_FILE)
    except Exception:
        os.remove(tmp_path)
        raise


def find_message(messages, message_id):
    for message in messages:
        if message.get("id") == message_id:
            return message
    return None


def parse_json_body(body):
    """Returns (data, ok). ok is False on invalid JSON."""
    if not body:
        return None, True
    try:
        return json.loads(body), True
    except json.JSONDecodeError:
        return None, False


class API:
    """A small decorator-based router, no regex or URL-pattern language:

    - @api.get(path)/@api.post(path)/@api.put(path)/@api.delete(path)
      register a handler for one exact, fixed path -- a plain dictionary
      lookup on (method, path). Used for the static whitelist (/,
      /index.html, ...) and for the /messages collection.
    - @api.get_id(prefix)/@api.post_id(prefix)/... register a handler for
      "<prefix>/<id>", where <id> is a run of digits; the matched id (as an
      int) is passed to the handler after the body. This is the one
      genuinely dynamic route this assignment needs (/messages/<id>).

    Anything that matches neither table falls through to whatever the
    caller does next (the generic static-file fallback in this file).
    """

    def __init__(self):
        self._routes = {}
        self._id_routes = {}

    def route(self, method, path):
        def decorator(func):
            self._routes[(method, path)] = func
            return func

        return decorator

    def get(self, path):
        return self.route("GET", path)

    def post(self, path):
        return self.route("POST", path)

    def put(self, path):
        return self.route("PUT", path)

    def delete(self, path):
        return self.route("DELETE", path)

    def default(self, func):
        """Shortcut for the homepage handler, served on GET /."""
        return self.route("GET", "/")(func)

    def route_id(self, method, prefix):
        def decorator(func):
            self._id_routes[(method, prefix)] = func
            return func

        return decorator

    def get_id(self, prefix):
        return self.route_id("GET", prefix)

    def post_id(self, prefix):
        return self.route_id("POST", prefix)

    def put_id(self, prefix):
        return self.route_id("PUT", prefix)

    def delete_id(self, prefix):
        return self.route_id("DELETE", prefix)

    def lookup(self, method, path):
        return self._routes.get((method, path))

    def lookup_id(self, method, prefix, path):
        """If path is exactly '<prefix>/<digits>', return (func, id);
        func is None if that id-shaped path isn't registered for this
        method. Returns None entirely if path isn't under prefix/<digits>
        at all."""
        if not path.startswith(prefix + "/"):
            return None
        remainder = path[len(prefix) + 1:]
        if not remainder.isdigit():
            return None
        return self._id_routes.get((method, prefix)), int(remainder)

    def run(self, host="localhost", port=8080):
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer((host, port), MyTCPHandler) as server:
            print(f"Serving at: http://{host}:{port}")
            server.serve_forever()


api = API()


class MyTCPHandler(socketserver.StreamRequestHandler):
    """
    This class is responsible for handling a request. The whole class is
    handed over as a parameter to the server instance so that it is capable
    of processing request. The server will use the handle-method to do this.
    It is instantiated once for each request!
    Since it inherits from the StreamRequestHandler class, it has two very
    usefull attributes you can use:

    rfile - This is the whole content of the request, displayed as a python
    file-like object. This means we can do readline(), readlines() on it!

    wfile - This is a file-like object which represents the response. We can
    write to it with write(). When we do wfile.close(), the response is
    automatically sent.
    """

    def handle(self):
        try:
            request_line = self._read_request_line()
            if request_line is None:
                return
            method, target, _version = request_line
            headers = self._read_headers()
            body = self._read_body(headers)
        except _BadRequest:
            self._send(400)
            return

        if method not in ("GET", "POST", "PUT", "DELETE"):
            self._send(501, b"Not Implemented", "text/plain")
            return

        path = unquote(urlsplit(target).path)

        func = api.lookup(method, path)
        if func is not None:
            func(self, body)
            return

        if path.startswith("/messages/"):
            found = api.lookup_id(method, "/messages", path)
            if found is not None:
                id_func, message_id = found
                if id_func is not None:
                    id_func(self, body, message_id)
                    return
            self._send(404, b"Not Found", "text/plain")
            return

        self._handle_static_fallback(method, path)

    # ---- Generic request parsing / response writing -----------------------

    def _read_request_line(self):
        raw_line = self.rfile.readline(65536)
        if raw_line in (b"", b"\r\n", b"\n"):
            # Tolerate a single leading blank line (RFC 9112 3), then require
            # a real request line.
            if raw_line == b"":
                return None
            raw_line = self.rfile.readline(65536)
            if raw_line == b"":
                return None
        line = raw_line.decode("iso-8859-1").rstrip("\r\n")
        parts = line.split(" ")
        if len(parts) != 3:
            raise _BadRequest()
        method, target, version = parts
        if not target.startswith("/") or not version.startswith("HTTP/"):
            raise _BadRequest()
        return method, target, version

    def _read_headers(self):
        headers = {}
        while True:
            raw_line = self.rfile.readline(65536)
            if raw_line in (b"", b"\r\n", b"\n"):
                break
            line = raw_line.decode("iso-8859-1").rstrip("\r\n")
            if ":" not in line:
                raise _BadRequest()
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        return headers

    def _read_body(self, headers):
        try:
            length = int(headers.get("content-length", 0))
        except ValueError:
            raise _BadRequest()
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _send(self, status, body=b"", content_type=None, extra_headers=None):
        reason = HTTP_STATUS_REASONS.get(status, "")
        lines = [
            f"HTTP/1.1 {status} {reason}",
            f"Server: {SERVER_NAME}",
            f"Date: {formatdate(usegmt=True)}",
            f"Content-Length: {len(body)}",
        ]
        if body and content_type:
            lines.append(f"Content-Type: {content_type}")
        if extra_headers:
            for key, value in extra_headers.items():
                lines.append(f"{key}: {value}")
        self.wfile.write(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1"))
        if body:
            self.wfile.write(body)

    # ---- Static file fallback (anything not in the whitelist below) -------

    def _handle_static_fallback(self, method, path):
        if method != "GET":
            self._send(403, b"Forbidden", "text/plain")
            return

        real_base = os.path.realpath(BASE_DIR)
        requested_path = os.path.normpath(os.path.join(BASE_DIR, path.lstrip("/")))
        real_requested = os.path.realpath(requested_path)
        if real_requested != real_base and not real_requested.startswith(real_base + os.sep):
            self._send(403, b"Forbidden", "text/plain")
            return

        if os.path.isfile(real_requested):
            # Exists on disk but isn't in the whitelist (e.g. server.py).
            self._send(403, b"Forbidden", "text/plain")
        else:
            self._send(404, b"Not Found", "text/plain")


# ---- /messages REST API ----------------------------------------------
# GET/POST/PUT/DELETE on the collection are exact-path routes; the id
# variants (/messages/<id>) go through the *_id() routes instead.

@api.get("/messages")
def list_messages(handler, body):
    _, messages = load_messages()
    handler._send(200, json.dumps(messages).encode("utf-8"), "application/json")


@api.post("/messages")
def create_message(handler, body):
    next_id, messages = load_messages()
    data, ok = parse_json_body(body)
    if not ok or not isinstance(data, dict) or not data.get("text"):
        handler._send(400, b"Bad Request", "text/plain")
        return
    new_message = {"id": next_id, "text": data["text"]}
    messages.append(new_message)
    save_messages(next_id + 1, messages)
    handler._send(201, json.dumps(new_message).encode("utf-8"), "application/json")


@api.put("/messages")
def update_message_by_body_id(handler, body):
    next_id, messages = load_messages()
    data, ok = parse_json_body(body)
    if not ok or not isinstance(data, dict) or "id" not in data or not data.get("text"):
        handler._send(400, b"Bad Request", "text/plain")
        return
    target = find_message(messages, data["id"])
    if target is None:
        handler._send(404, b"Not Found", "text/plain")
        return
    target["text"] = data["text"]
    save_messages(next_id, messages)
    handler._send(200, json.dumps(target).encode("utf-8"), "application/json")


@api.delete("/messages")
def delete_message_by_body_id(handler, body):
    next_id, messages = load_messages()
    data, ok = parse_json_body(body)
    if not ok or not isinstance(data, dict) or "id" not in data:
        handler._send(400, b"Bad Request", "text/plain")
        return
    target = find_message(messages, data["id"])
    if target is None:
        handler._send(404, b"Not Found", "text/plain")
        return
    messages.remove(target)
    save_messages(next_id, messages)
    handler._send(200, json.dumps(target).encode("utf-8"), "application/json")


@api.get_id("/messages")
def get_message(handler, body, message_id):
    _, messages = load_messages()
    target = find_message(messages, message_id)
    if target is None:
        handler._send(404, b"Not Found", "text/plain")
        return
    handler._send(200, json.dumps(target).encode("utf-8"), "application/json")


@api.put_id("/messages")
def update_message_by_url_id(handler, body, message_id):
    next_id, messages = load_messages()
    data, ok = parse_json_body(body)
    if not ok or not isinstance(data, dict) or not data.get("text"):
        handler._send(400, b"Bad Request", "text/plain")
        return
    target = find_message(messages, message_id)
    if target is None:
        handler._send(404, b"Not Found", "text/plain")
        return
    target["text"] = data["text"]
    save_messages(next_id, messages)
    handler._send(200, json.dumps(target).encode("utf-8"), "application/json")


@api.delete_id("/messages")
def delete_message_by_url_id(handler, body, message_id):
    next_id, messages = load_messages()
    target = find_message(messages, message_id)
    if target is None:
        handler._send(404, b"Not Found", "text/plain")
        return
    messages.remove(target)
    save_messages(next_id, messages)
    handler._send(200, json.dumps(target).encode("utf-8"), "application/json")


@api.post_id("/messages")
def post_to_message_item(handler, body, message_id):
    # Creating a message at a URL that already names a specific id doesn't
    # make sense; only the collection endpoint accepts creation.
    handler._send(403, b"Forbidden", "text/plain")


# ---- Static file whitelist ------------------------------------------------
# The only routes served or written outside of /messages. Anything else
# falls through to _handle_static_fallback above (403 if it exists on disk,
# 404 otherwise) -- a whitelist, not a blacklist.

def _serve_static_file(handler, filename):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.isfile(file_path):
        handler._send(404, b"Not Found", "text/plain")
        return
    content_type = CONTENT_TYPES.get(os.path.splitext(filename)[1], "application/octet-stream")
    with open(file_path, "rb") as infile:
        content = infile.read()
    handler._send(200, content, content_type)


@api.default
@api.get("/index.html")
def serve_index(handler, body):
    _serve_static_file(handler, "index.html")


@api.get("/favicon.ico")
def serve_favicon(handler, body):
    _serve_static_file(handler, "favicon.ico")


@api.get("/test.txt")
def serve_test_txt(handler, body):
    _serve_static_file(handler, "test.txt")


@api.post("/test.txt")
def post_test_txt(handler, body):
    target_path = os.path.join(BASE_DIR, "test.txt")
    with open(target_path, "ab") as outfile:
        outfile.write(body)
    with open(target_path, "rb") as infile:
        content = infile.read()
    handler._send(200, content, "text/plain")


if __name__ == "__main__":
    api.run("localhost", 8080)
