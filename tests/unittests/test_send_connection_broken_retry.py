import unittest
from unittest import mock
import requests
from urllib3.exceptions import IncompleteRead, ProtocolError
from tap_jira import http


class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.json_data = json_data or {}

    def json(self):
        return self.json_data


OK = MockResponse(200, {"issues": []})
CONFIG = {"username": "u", "password": "p", "base_url": "mock_base_url"}
CHUNK_ERROR = requests.exceptions.ChunkedEncodingError(
    ProtocolError("Connection broken: InvalidChunkLength(got length b'', 0 bytes read)"))


@mock.patch("time.sleep")
@mock.patch("tap_jira.http.Client.test_basic_credentials_are_authorized")
class TestSendConnectionBrokenRetry(unittest.TestCase):

    @mock.patch("tap_jira.http.requests.Session.send", side_effect=[CHUNK_ERROR, OK])
    def test_chunked_encoding_error_is_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        result = client.request("issues", "GET", "/rest/api/2/search/jql")
        self.assertEqual(result, {"issues": []})
        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("tap_jira.http.requests.Session.send", side_effect=[ProtocolError("Connection broken"), OK])
    def test_protocol_error_is_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        result = client.request("issues", "GET", "/rest/api/2/search/jql")
        self.assertEqual(result, {"issues": []})
        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("tap_jira.http.requests.Session.send", side_effect=[IncompleteRead(0, 10), OK])
    def test_incomplete_read_is_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        result = client.request("issues", "GET", "/rest/api/2/search/jql")
        self.assertEqual(result, {"issues": []})
        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("tap_jira.http.requests.Session.send", side_effect=[CHUNK_ERROR] * 6)
    def test_chunked_encoding_error_gives_up_after_max_tries(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        with self.assertRaises(requests.exceptions.ChunkedEncodingError):
            client.request("issues", "GET", "/rest/api/2/search/jql")
        self.assertEqual(mock_send.call_count, 6)
