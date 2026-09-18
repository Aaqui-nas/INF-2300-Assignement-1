# INF-2300 Assignment 1 — HTTP server & RESTful API

## Running the server

```
python3 server.py
```

The server listens on `localhost:8080` and serves files relative to this
directory (`src/`).

## Running the tests

```
python3 test_client.py
```

Provided precode, unmodified. Starts the handler on a second port
(`localhost:54321`) and tests the static file part only (GET/POST, status
codes, headers, path traversal), sequentially then in random order (skips
the random pass if the sequential pass didn't fully succeed).

```
python3 test_messages.py
```

Our own suite, covering everything `test_client.py` doesn't: the `/messages`
REST API (GET/POST/PUT/DELETE on the collection and on `/messages/<id>`),
the edge cases discussed in the report (missing/invalid fields, non-existent
ids, malformed JSON, POST to an id URL), persistence to disk, and unsupported
HTTP methods (`HEAD`, a made-up verb). Runs its own handler on
`localhost:54322` so it can be run independently of, or alongside,
`test_client.py`. Every test creates and cleans up its own message(s), so
the suite also runs safely in random order.

## Endpoints

### Static file server

| Method | Path          | Behaviour                                      |
|--------|---------------|-------------------------------------------------|
| GET    | `/`           | Returns `index.html`                            |
| GET    | `/index.html` | Returns `index.html`                             |
| GET    | `/favicon.ico`| Returns the favicon                              |
| GET    | `/test.txt`   | Returns `test.txt` (once it exists)              |
| POST   | `/test.txt`   | Appends the request body, returns the full file  |

Any other GET target that exists on disk (e.g. `/server.py`) returns
`403 Forbidden` (whitelist, not blacklist); anything that doesn't exist
returns `404 Not Found`. Requests that resolve outside `src/` (path
traversal) return `403 Forbidden`.

### `/messages` REST API

JSON message objects look like `{"id": 1, "text": "..."}`.

| Method | Path              | Behaviour                                             |
|--------|-------------------|--------------------------------------------------------|
| GET    | `/messages`       | List all messages                                       |
| POST   | `/messages`       | Create a message from `{"text": ...}`, returns 201       |
| PUT    | `/messages`       | Update by `{"id": ..., "text": ...}`                     |
| DELETE | `/messages`       | Delete by `{"id": ...}`                                  |
| GET    | `/messages/<id>`  | Get one message by id in the URL                         |
| PUT    | `/messages/<id>`  | Update by `{"text": ...}`, id taken from the URL          |
| DELETE | `/messages/<id>`  | Delete by id in the URL                                   |

Messages are persisted to `messages.json` in this directory (created
automatically on first write, survives server restarts).
