import json
import socketserver
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from random import shuffle

import server
from server import MyTCPHandler as HTTPHandler

"""
Automated tests for the /messages REST API (GET/POST/PUT/DELETE on the
collection and on /messages/<id>), plus a couple of generic edge cases
(unsupported HTTP methods) that test_client.py doesn't cover -- it only
exercises the static file part, by design (see its module docstring/README).

Every test below creates whatever data it needs and cleans up after itself,
so tests stay independent of each other and of execution order (this file
supports the same sequential-then-random run pattern as test_client.py).
"""

RANDOM_TESTING_ORDER = True

HOST = "localhost"
PORT = 54322


class MockServer(socketserver.TCPServer):
    allow_reuse_address = True


mock_server = MockServer((HOST, PORT), HTTPHandler)
server_thread = threading.Thread(target=mock_server.serve_forever)
server_thread.start()
client = HTTPConnection(HOST, PORT)


def _request(method, path, payload=None):
    """Send a request, optionally with a JSON payload, and return
    (status, parsed_json_or_None, raw_body)."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    client.request(method, path, body=body, headers=headers)
    response = client.getresponse()
    status = response.status
    raw = response.read()
    client.close()
    try:
        data = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        data = None
    return status, data, raw


def _create_message(text="Test message"):
    status, data, _ = _request("POST", "/messages", {"text": text})
    assert status == HTTPStatus.CREATED, f"setup failed: POST /messages returned {status}"
    return data["id"]


def _delete_message(message_id):
    _request("DELETE", f"/messages/{message_id}")


def test_get_messages_returns_a_json_array():
    """GET /messages returns a JSON list."""
    status, data, _ = _request("GET", "/messages")
    return status == HTTPStatus.OK and isinstance(data, list)


def test_post_creates_message_with_201():
    """POST /messages creates a message and returns 201 with id + text."""
    status, data, _ = _request("POST", "/messages", {"text": "Example text"})
    ok = (
        status == HTTPStatus.CREATED
        and isinstance(data, dict)
        and data.get("text") == "Example text"
        and isinstance(data.get("id"), int)
    )
    if isinstance(data, dict) and "id" in data:
        _delete_message(data["id"])
    return ok


def test_created_message_is_visible_in_collection():
    """A created message shows up in a subsequent GET /messages."""
    message_id = _create_message("Visible in collection")
    _, data, _ = _request("GET", "/messages")
    ok = isinstance(data, list) and any(m.get("id") == message_id for m in data)
    _delete_message(message_id)
    return ok


def test_post_without_text_is_bad_request():
    """POST /messages with no 'text' field returns 400."""
    status, _, _ = _request("POST", "/messages", {})
    return status == HTTPStatus.BAD_REQUEST


def test_post_ignores_client_supplied_id():
    """The server assigns its own id; a client-supplied id in POST is ignored."""
    status, data, _ = _request("POST", "/messages", {"id": 999999, "text": "Spoofed id"})
    ok = status == HTTPStatus.CREATED and data.get("id") != 999999
    if isinstance(data, dict) and "id" in data:
        _delete_message(data["id"])
    return ok


def test_get_message_by_url_id():
    """GET /messages/<id> returns that single message."""
    message_id = _create_message("Fetch me by id")
    status, data, _ = _request("GET", f"/messages/{message_id}")
    ok = status == HTTPStatus.OK and data == {"id": message_id, "text": "Fetch me by id"}
    _delete_message(message_id)
    return ok


def test_get_nonexistent_id_returns_404():
    """GET /messages/<id> for an id that was deleted returns 404."""
    message_id = _create_message("Temporary")
    _delete_message(message_id)
    status, _, _ = _request("GET", f"/messages/{message_id}")
    return status == HTTPStatus.NOT_FOUND


def test_get_non_digit_id_returns_404():
    """GET /messages/<non-digit> (not a valid id shape) returns 404."""
    status, _, _ = _request("GET", "/messages/abc")
    return status == HTTPStatus.NOT_FOUND


def test_put_updates_by_body_id():
    """PUT /messages with {id, text} in the body updates that message."""
    message_id = _create_message("Before update")
    status, data, _ = _request("PUT", "/messages", {"id": message_id, "text": "After update"})
    ok = status == HTTPStatus.OK and data.get("text") == "After update"
    _delete_message(message_id)
    return ok


def test_put_updates_by_url_id():
    """PUT /messages/<id> with {text} updates the message named in the URL."""
    message_id = _create_message("Before update (url)")
    status, data, _ = _request("PUT", f"/messages/{message_id}", {"text": "After update (url)"})
    ok = status == HTTPStatus.OK and data.get("text") == "After update (url)"
    _delete_message(message_id)
    return ok


def test_put_without_id_in_body_is_bad_request():
    """PUT /messages with no 'id' field returns 400, not 404."""
    status, _, _ = _request("PUT", "/messages", {"text": "no id here"})
    return status == HTTPStatus.BAD_REQUEST


def test_put_existing_id_without_text_is_bad_request():
    """PUT /messages with a valid id but no 'text' field returns 400."""
    message_id = _create_message("Has text")
    status, _, _ = _request("PUT", "/messages", {"id": message_id})
    _delete_message(message_id)
    return status == HTTPStatus.BAD_REQUEST


def test_put_nonexistent_id_returns_404():
    """PUT /messages with a well-formed but nonexistent id returns 404."""
    message_id = _create_message("Temporary")
    _delete_message(message_id)
    status, _, _ = _request("PUT", "/messages", {"id": message_id, "text": "too late"})
    return status == HTTPStatus.NOT_FOUND


def test_delete_by_body_id():
    """DELETE /messages with {id} in the body removes that message."""
    message_id = _create_message("Delete me")
    status, data, _ = _request("DELETE", "/messages", {"id": message_id})
    ok = status == HTTPStatus.OK and data.get("id") == message_id
    get_status, _, _ = _request("GET", f"/messages/{message_id}")
    return ok and get_status == HTTPStatus.NOT_FOUND


def test_delete_by_url_id():
    """DELETE /messages/<id> removes the message named in the URL."""
    message_id = _create_message("Delete me too")
    status, data, _ = _request("DELETE", f"/messages/{message_id}")
    ok = status == HTTPStatus.OK and data.get("id") == message_id
    get_status, _, _ = _request("GET", f"/messages/{message_id}")
    return ok and get_status == HTTPStatus.NOT_FOUND


def test_delete_without_id_is_bad_request():
    """DELETE /messages with no 'id' field returns 400."""
    status, _, _ = _request("DELETE", "/messages", {})
    return status == HTTPStatus.BAD_REQUEST


def test_delete_nonexistent_id_returns_404():
    """DELETE /messages for an id that doesn't exist returns 404."""
    message_id = _create_message("Temporary")
    _delete_message(message_id)
    status, _, _ = _request("DELETE", "/messages", {"id": message_id})
    return status == HTTPStatus.NOT_FOUND


def test_post_to_item_url_is_forbidden():
    """POST /messages/<id> (creating at an id-specific URL) returns 403."""
    message_id = _create_message("Anchor")
    status, _, _ = _request("POST", f"/messages/{message_id}", {"text": "nope"})
    _delete_message(message_id)
    return status == HTTPStatus.FORBIDDEN


def test_malformed_json_body_is_bad_request():
    """A syntactically invalid JSON body returns 400."""
    client.request("POST", "/messages", body=b"{not valid json", headers={"Content-Type": "application/json"})
    response = client.getresponse()
    status = response.status
    response.read()
    client.close()
    return status == HTTPStatus.BAD_REQUEST


def test_empty_post_body_is_bad_request():
    """POST /messages with an empty body returns 400 (missing 'text')."""
    client.request("POST", "/messages")
    response = client.getresponse()
    status = response.status
    response.read()
    client.close()
    return status == HTTPStatus.BAD_REQUEST


def test_messages_are_persisted_to_disk():
    """A created message is readable back via load_messages() (the same
    on-disk state a fresh server process would load on restart)."""
    message_id = _create_message("Should survive a restart")
    _, messages = server.load_messages()
    ok = any(m.get("id") == message_id and m.get("text") == "Should survive a restart" for m in messages)
    _delete_message(message_id)
    return ok


def test_unsupported_method_returns_not_implemented():
    """An unimplemented HTTP method (HEAD) never crashes the server: 501."""
    client.request("HEAD", "/")
    response = client.getresponse()
    status = response.status
    response.read()
    client.close()
    return status == HTTPStatus.NOT_IMPLEMENTED


def test_nonsense_method_returns_not_implemented():
    """A made-up HTTP method (PIZZA) never crashes the server: 501."""
    client.request("PIZZA", "/")
    response = client.getresponse()
    status = response.status
    response.read()
    client.close()
    return status == HTTPStatus.NOT_IMPLEMENTED


test_functions = [
    test_get_messages_returns_a_json_array,
    test_post_creates_message_with_201,
    test_created_message_is_visible_in_collection,
    test_post_without_text_is_bad_request,
    test_post_ignores_client_supplied_id,
    test_get_message_by_url_id,
    test_get_nonexistent_id_returns_404,
    test_get_non_digit_id_returns_404,
    test_put_updates_by_body_id,
    test_put_updates_by_url_id,
    test_put_without_id_in_body_is_bad_request,
    test_put_existing_id_without_text_is_bad_request,
    test_put_nonexistent_id_returns_404,
    test_delete_by_body_id,
    test_delete_by_url_id,
    test_delete_without_id_is_bad_request,
    test_delete_nonexistent_id_returns_404,
    test_post_to_item_url_is_forbidden,
    test_malformed_json_body_is_bad_request,
    test_empty_post_body_is_bad_request,
    test_messages_are_persisted_to_disk,
    test_unsupported_method_returns_not_implemented,
    test_nonsense_method_returns_not_implemented,
]


def run_tests(all_tests):
    passed = 0
    num_tests = len(all_tests)
    for test_function in all_tests:
        result = test_function()
        if result:
            passed += 1
        print(("FAIL", "PASS")[result] + "\t" + test_function.__doc__)
    percent = round((passed / num_tests) * 100, 2)
    print(f"\n{passed} of {num_tests}({percent}%) tests PASSED.\n")
    return passed == num_tests


def run():
    print("Running /messages tests in sequential order...\n")
    sequential_passed = run_tests(test_functions)
    if RANDOM_TESTING_ORDER and sequential_passed:
        print("Running /messages tests in random order...\n")
        shuffle(test_functions)
        run_tests(test_functions)
    elif RANDOM_TESTING_ORDER and not sequential_passed:
        print("Tests should run in sequential order first.\n")


run()
mock_server.shutdown()
