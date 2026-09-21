import os
import unittest
from unittest.mock import Mock, patch

from instagram_client import InstagramAPIError, InstagramClient, InstagramConfig


class InstagramClientTests(unittest.TestCase):
    def setUp(self):
        self.client = InstagramClient(
            InstagramConfig("secret", "123", "v26.0", "https://graph.instagram.com")
        )

    @patch("instagram_client.requests.Session.request")
    def test_create_reel_uses_expected_endpoint_and_fields(self, request):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"id": "container-1"}
        request.return_value = response
        result = self.client.create_reel_container(
            "https://cdn.example/video.mp4", "hello", is_ai_generated=True
        )
        self.assertEqual(result, "container-1")
        _, url = request.call_args.args
        self.assertEqual(url, "https://graph.instagram.com/v26.0/123/media")
        self.assertEqual(request.call_args.kwargs["json"]["media_type"], "REELS")
        self.assertTrue(request.call_args.kwargs["json"]["is_ai_generated"])

    @patch("instagram_client.requests.Session.request")
    def test_api_error_does_not_leak_token(self, request):
        response = Mock(ok=False, status_code=400)
        response.json.return_value = {"error": {"message": "Bad request", "code": 100}}
        request.return_value = response
        with self.assertRaisesRegex(InstagramAPIError, "Bad request") as caught:
            self.client.get_profile()
        self.assertNotIn("secret", str(caught.exception))

    def test_env_requires_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                InstagramConfig.from_env()


if __name__ == "__main__":
    unittest.main()

