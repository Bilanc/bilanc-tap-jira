import unittest
from unittest import mock
from tap_jira import http


class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.json_data = json_data or {}

    def json(self):
        return self.json_data


OK = MockResponse(200, {"values": []})
PATH = "/rest/api/2/group/member"
CONFIG = {"username": "u", "password": "p", "base_url": "mock_base_url"}
RETRIED = {
    500: http.JiraInternalServerError,
    502: http.JiraBadGatewayError,
    504: http.JiraGatewayTimeoutError,
}


@mock.patch("time.sleep")
@mock.patch("tap_jira.http.Client.test_basic_credentials_are_authorized")
class TestServerErrorRetry(unittest.TestCase):

    def test_transient_server_error_is_retried(self, mock_auth_check, mock_sleep):
        for status in RETRIED:
            with self.subTest(status=status), \
                    mock.patch("tap_jira.http.Client.send",
                               side_effect=[MockResponse(status), OK]) as mock_send:
                client = http.Client(CONFIG, None)
                result = client.request("users", "GET", PATH)
                self.assertEqual(result, {"values": []})
                self.assertEqual(mock_send.call_count, 2)

    def test_server_error_gives_up_after_max_tries(self, mock_auth_check, mock_sleep):
        for status, exc in RETRIED.items():
            with self.subTest(status=status), \
                    mock.patch("tap_jira.http.Client.send",
                               side_effect=[MockResponse(status)] * 10) as mock_send:
                client = http.Client(CONFIG, None)
                with self.assertRaises(exc):
                    client.request("users", "GET", PATH)
                self.assertEqual(mock_send.call_count, 10)

    @mock.patch("tap_jira.http.Client.send", side_effect=[MockResponse(501), OK])
    def test_not_implemented_is_not_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        with self.assertRaises(http.JiraNotImplementedError):
            client.request("users", "GET", PATH)
        self.assertEqual(mock_send.call_count, 1)
