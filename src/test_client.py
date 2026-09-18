import socketserver
import threading
from server import MyTCPHandler as HTTPHandler
from http import HTTPStatus
from http.client import HTTPConnection, BadStatusLine
import os
from random import shuffle

"""
Written by: Raymon Skjørten Hansen
Email: raymon.s.hansen@uit.no
Course: INF-2300 - Networking
UiT - The Arctic University of Norway
May 9th, 2019
"""


RANDOM_TESTING_ORDER = True

HOST = "localhost"
PORT = 54321

with open("index.html", "rb") as infile:
    EXPECTED_BODY = infile.read()

with open("server.py", "rb") as infile:
    FORBIDDEN_BODY = infile.read()


class MockServer(socketserver.TCPServer):
    allow_reuse_address = True


server = MockServer((HOST, PORT), HTTPHandler)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.start()
client = HTTPConnection(HOST, PORT)


def server_returns_valid_response_code():
    """Server returns a valid http-response code."""
    client.request("GET", "/")
    try:
        response = client.getresponse()
        client.close()
        return response.status in [status.value for status in HTTPStatus]
    except BadStatusLine:
        client.close()
        return False


def test_index():
    """GET-request to root returns 'index.html'."""
    client.request("GET", "/")
    body = client.getresponse().read()
    client.close()
    return EXPECTED_BODY == body


def test_content_length():
    """Content-Length header is present."""
    client.request("GET", "/")
    headers = [k.lower() for k in client.getresponse().headers.keys()]
    client.close()
    return "content-length" in headers


def test_valid_content_length():
    """Content-Length is correct."""
    client.request("GET", "/")
    headers = {k.lower(): v for k, v in client.getresponse().headers.items()}
    expected_length = len(EXPECTED_BODY)
    try:
        length = int(headers.get("content-length"))
        return expected_length == length
    except (KeyError, TypeError):
        return False
    finally:
        client.close()


def test_content_type():
    """Content-Type is present."""
    client.request("GET", "/")
    headers = [k.lower() for k in client.getresponse().headers.keys()]
    client.close()
    return "content-type" in headers


def test_valid_content_type():
    """Content type is correct."""
    client.request("GET", "/")
    headers = {k.lower(): v for k, v in client.getresponse().headers.items()}
    expected_type = "text/html"
    try:
        actual_type = headers.get("content-type")
        # Type-field could contain character encoding too.
        # So we just check that the basic type is correct.
        return actual_type.startswith(expected_type)
    except (KeyError, TypeError):
        return False
    finally:
        client.close()


def test_nonexistent_resource_status_code():
    """Server returns 404 on non-existing resource."""
    client.request("GET", "/did_not_find_this_file.not")
    response = client.getresponse()
    client.close()
    return response.status == HTTPStatus.NOT_FOUND


def test_forbidden_resource_status_code():
    """Server returns 403 on forbidden resource."""
    client.request("GET", "/server.py")
    response = client.getresponse()
    client.close()
    return response.status == HTTPStatus.FORBIDDEN


def test_directory_traversal_exploit():
    """Directory traversal attack returns 403 status code."""
    client.request("GET", "/../README.md")
    response = client.getresponse()
    client.close()
    return response.status == HTTPStatus.FORBIDDEN


def test_post_to_non_existing_file_should_create_file():
    """POST-request to non-existing file, should create that file."""
    testfile = "test.txt"
    msg = b'Simple test'
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        "Accept": "text/plain",
        "Content-Length": len(msg),
    }
    if(os.path.exists(testfile)):
        os.remove(testfile)
    client.request("POST", "/" + testfile, body=msg, headers=headers)
    client.getresponse()
    client.close()
    return os.path.exists(testfile)


def test_post_to_test_file_should_return_file_content():
    """POST to test-file should append to file and return the file-content."""
    testfile = "test.txt"
    msg = b'text=Simple test'
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        "Accept": "text/plain",
        "Content-Length": len(msg),
    }
    if(os.path.exists(testfile)):
        os.remove(testfile)
    client.request("POST", "/" + testfile, body=msg, headers=headers)
    response_body = client.getresponse().read()
    with open(testfile, "rb") as infile:
        filecontent = infile.read()
    client.close()
    return response_body == filecontent


def test_post_to_test_file_should_return_correct_content_length():
    """POST to test-file should respond with correct content_length."""
    testfile = "test.txt"
    msg = b'text=Simple test'
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        "Accept": "text/plain",
        "Content-Length": len(msg),
    }
    if(os.path.exists(testfile)):
        os.remove(testfile)
    client.request("POST", "/" + testfile, body=msg, headers=headers)
    expected_content_length = len(client.getresponse().read())
    with open(testfile, "rb") as infile:
        actual_length = len(infile.read())
    client.close()
    return expected_content_length == actual_length


test_functions = [
    server_returns_valid_response_code,
    test_index,
    test_content_length,
    test_valid_content_length,
    test_content_type,
    test_valid_content_type,
    test_nonexistent_resource_status_code,
    test_forbidden_resource_status_code,
    test_directory_traversal_exploit,
    test_post_to_non_existing_file_should_create_file,
    test_post_to_test_file_should_return_file_content,
    test_post_to_test_file_should_return_correct_content_length,
]


def run_tests(all_tests, random=False):
    passed = 0
    num_tests = len(all_tests)
    skip_rest = False
    for test_function in all_tests:
        if not skip_rest:
            result = test_function()
            if result:
                passed += 1
            else:
                skip_rest = True
            print(("FAIL", "PASS")[result] + "\t" + test_function.__doc__)
        else:
            print("SKIP\t" + test_function.__doc__)
    percent = round((passed / num_tests) * 100, 2)
    print(f"\n{passed} of {num_tests}({percent}%) tests PASSED.\n")
    if passed == num_tests:
        return True
    else:
        return False


def run():
    print("Running tests in sequential order...\n")
    sequential_passed = run_tests(test_functions)
    # We only allow random if all tests pass sequentially
    if RANDOM_TESTING_ORDER and sequential_passed:
        print("Running tests in random order...\n")
        shuffle(test_functions)
        run_tests(test_functions, True)
    elif RANDOM_TESTING_ORDER and not sequential_passed:
        print("Tests should run in sequential order first.\n")


run()
server.shutdown()
