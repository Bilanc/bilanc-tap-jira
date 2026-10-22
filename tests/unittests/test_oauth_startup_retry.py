import json
import unittest
from unittest import mock
import requests
from requests.exceptions import HTTPError
from tap_jira import http


class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.json_data = json_data if json_data is not None else {}
        self.text = json.dumps(self.json_data)

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError("{} Server Error".format(self.status_code), response=self)


SERVICE_UNAVAILABLE = MockResponse(503, {"message": "Service Unavailable"})
TOO_MANY_REQUESTS = MockResponse(429, {"message": "Too Many Requests"})
RESOURCES_OK = MockResponse(200, [{"id": "cloud-123", "name": "bilanc"}])
TOKEN_OK = MockResponse(200, {"access_token": "new-access", "refresh_token": "new-refresh"})
CLOUD_CONFIG = {"client_id": "cid", "client_secret": "csecret", "access_token": "a",
                "refresh_token": "r", "site_name": "bilanc"}


@mock.patch("time.sleep")
@mock.patch("tap_jira.http.Client.test_credentials_are_authorized")
@mock.patch("tap_jira.http.Client.refresh_credentials")
class TestAccessibleResourcesRetry(unittest.TestCase):

    @mock.patch("tap_jira.http.requests.request", side_effect=[SERVICE_UNAVAILABLE, RESOURCES_OK])
    def test_503_from_accessible_resources_is_retried(self, mock_request, mock_refresh, mock_auth_check, mock_sleep):
        client = http.Client(CLOUD_CONFIG, None)
        self.assertEqual(client.cloud_id, "cloud-123")
        self.assertEqual(mock_request.call_count, 2)

    @mock.patch("tap_jira.http.requests.request", side_effect=[TOO_MANY_REQUESTS, RESOURCES_OK])
    def test_429_from_accessible_resources_is_retried(self, mock_request, mock_refresh, mock_auth_check, mock_sleep):
        client = http.Client(CLOUD_CONFIG, None)
        self.assertEqual(client.cloud_id, "cloud-123")
        self.assertEqual(mock_request.call_count, 2)

    @mock.patch("tap_jira.http.requests.request", side_effect=[SERVICE_UNAVAILABLE] * 6)
    def test_503_from_accessible_resources_gives_up_after_max_tries(self, mock_request, mock_refresh, mock_auth_check, mock_sleep):
        with self.assertRaises(HTTPError):
            http.Client(CLOUD_CONFIG, None)
        self.assertEqual(mock_request.call_count, 6)

    @mock.patch("tap_jira.http.requests.request", side_effect=[MockResponse(401, {}), RESOURCES_OK])
    def test_4xx_from_accessible_resources_is_not_retried(self, mock_request, mock_refresh, mock_auth_check, mock_sleep):
        with self.assertRaises(HTTPError):
            http.Client(CLOUD_CONFIG, None)
        self.assertEqual(mock_request.call_count, 1)

    @mock.patch("tap_jira.http.requests.request", side_effect=[requests.exceptions.ConnectionError("boom"), RESOURCES_OK])
    def test_connection_error_from_accessible_resources_is_retried(self, mock_request, mock_refresh, mock_auth_check, mock_sleep):
        client = http.Client(CLOUD_CONFIG, None)
        self.assertEqual(client.cloud_id, "cloud-123")
        self.assertEqual(mock_request.call_count, 2)


@mock.patch("time.sleep")
@mock.patch("threading.Timer")
@mock.patch("tap_jira.http.Client.test_credentials_are_authorized")
@mock.patch("tap_jira.http.Client._get_cloud_id", return_value="cloud-123")
class TestRefreshTokenRetry(unittest.TestCase):

    def _client(self, post_side_effect):
        with mock.patch("tap_jira.http.open", mock.mock_open(read_data=json.dumps(CLOUD_CONFIG)), create=True), \
                mock.patch.object(requests.Session, "post", side_effect=post_side_effect) as mock_post:
            client = http.Client(CLOUD_CONFIG, "config.json")
        return client, mock_post

    def test_503_from_token_endpoint_is_retried(self, mock_cloud_id, mock_auth_check, mock_timer, mock_sleep):
        client, mock_post = self._client([SERVICE_UNAVAILABLE, TOKEN_OK])
        self.assertEqual(client.access_token, "new-access")
        self.assertEqual(client.refresh_token, "new-refresh")
        self.assertEqual(mock_post.call_count, 2)
        mock_timer.assert_called_once()

    def test_429_from_token_endpoint_is_retried(self, mock_cloud_id, mock_auth_check, mock_timer, mock_sleep):
        client, mock_post = self._client([TOO_MANY_REQUESTS, TOKEN_OK])
        self.assertEqual(client.access_token, "new-access")
        self.assertEqual(mock_post.call_count, 2)
        mock_timer.assert_called_once()

    def test_connection_error_from_token_endpoint_does_not_start_timer(self, mock_cloud_id, mock_auth_check, mock_timer, mock_sleep):
        with mock.patch("tap_jira.http.open", mock.mock_open(read_data=json.dumps(CLOUD_CONFIG)), create=True), \
                mock.patch.object(requests.Session, "post", side_effect=requests.exceptions.ConnectionError("boom")) as mock_post:
            with self.assertRaises(Exception):
                http.Client(CLOUD_CONFIG, "config.json")
        self.assertEqual(mock_post.call_count, 6)
        mock_timer.assert_not_called()

    def test_503_from_token_endpoint_gives_up_after_max_tries(self, mock_cloud_id, mock_auth_check, mock_timer, mock_sleep):
        with mock.patch("tap_jira.http.open", mock.mock_open(read_data=json.dumps(CLOUD_CONFIG)), create=True), \
                mock.patch.object(requests.Session, "post", side_effect=[SERVICE_UNAVAILABLE] * 6) as mock_post:
            with self.assertRaises(Exception) as ctx:
                http.Client(CLOUD_CONFIG, "config.json")
        self.assertEqual(mock_post.call_count, 6)
        self.assertIn("Service Unavailable", str(ctx.exception))
        mock_timer.assert_not_called()

    def test_4xx_from_token_endpoint_is_not_retried(self, mock_cloud_id, mock_auth_check, mock_timer, mock_sleep):
        with mock.patch("tap_jira.http.open", mock.mock_open(read_data=json.dumps(CLOUD_CONFIG)), create=True), \
                mock.patch.object(requests.Session, "post", side_effect=[MockResponse(400, {"error": "invalid_grant"}), TOKEN_OK]) as mock_post:
            with self.assertRaises(Exception):
                http.Client(CLOUD_CONFIG, "config.json")
        self.assertEqual(mock_post.call_count, 1)
