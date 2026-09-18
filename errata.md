# Errata
List of known errors in the precode for Assignment 1 in INF-2300.
The document is subject to change.

Document Version: 1.0
Last updated: 03.09.26

## 1
### Name:
Invalid targets in `test_client.py`

### Description:
All request targets (paths) must start with a `/` according to the related RFCs. See [RFC 9112 3.2.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-3.2.1) and [RFC 9110 Apendix A ](https://www.rfc-editor.org/rfc/rfc9110.html#appendix-A).

This condition is breached in several tests in `test_client.py`.
The requests from the test client are missing the leading `/`.
Due to this error, the tests are incorrectly validating the API functionality implemented in `server.py`.

### Suggested fix:
Update the targets in the affected tests so that they all start with a `/`. For example:
`/server.py` instead of `server.py`

### Affected tests:
```
test_nonexistent_resource_status_code
test_forbidden_resource_status_code
test_directory_traversal_exploit
test_post_to_non_existing_file_should_create_file
test_post_to_test_file_should_return_file_content
test_post_to_test_file_should_return_correct_content_length
```

### Supplementary comment:
A request without a leading `/` should result in a 400 bad request response from your API.

### Credit:
Benjamin Aaboe Mjaatvedt