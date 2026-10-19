import unittest
from unittest import mock
from tap_jira import http


class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.json_data = json_data or {}

    def json(self):
        return self.json_data


NOT_FOUND = MockResponse(404, {"errorMessages": ["Issue does not exist or you do not have permission to see it."]})
OK = MockResponse(200, {"issues": []})
SEARCH_PATH = "/rest/api/2/search/jql"
CONFIG = {"username": "u", "password": "p", "base_url": "mock_base_url"}


@mock.patch("time.sleep")
@mock.patch("tap_jira.http.Client.test_basic_credentials_are_authorized")
class TestSearchNotFoundRetry(unittest.TestCase):

    @mock.patch("tap_jira.http.Client.send", side_effect=[NOT_FOUND, OK])
    def test_search_404_is_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        result = client.request("issues", "GET", SEARCH_PATH, params={"jql": "updated >= '2026-10-18 10:56'"})
        self.assertEqual(result, {"issues": []})
        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("tap_jira.http.Client.send", side_effect=[NOT_FOUND] * 4)
    def test_search_404_gives_up_after_max_tries(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        with self.assertRaises(http.JiraTransientNotFoundError) as ctx:
            client.request("issues", "GET", SEARCH_PATH)
        self.assertEqual(mock_send.call_count, 4)
        self.assertIn("Issue does not exist", str(ctx.exception))

    @mock.patch("tap_jira.http.Client.send", side_effect=[NOT_FOUND, OK])
    def test_other_404_is_not_retried(self, mock_send, mock_auth_check, mock_sleep):
        client = http.Client(CONFIG, None)
        with self.assertRaises(http.JiraNotFoundError) as ctx:
            client.request("projects", "GET", "/rest/api/2/project/search")
        self.assertNotIsInstance(ctx.exception, http.JiraTransientNotFoundError)
        self.assertEqual(mock_send.call_count, 1)
