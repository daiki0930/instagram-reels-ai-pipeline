import tempfile
import unittest
from pathlib import Path

from app import create_app
from store import JobStore


class FakeInstagramClient:
    def __init__(self, status="FINISHED"):
        self.status = status
        self.publish_calls = 0

    def get_container_status(self, container_id):
        return self.status

    def publish_container(self, container_id):
        self.publish_calls += 1
        return "media-1"

    def get_media(self, media_id):
        return {"id": media_id, "permalink": "https://instagram.example/reel/1"}


class ApprovalFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "test.db")
        self.fake = FakeInstagramClient()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE": self.db,
            "INSTAGRAM_CLIENT_FACTORY": lambda: self.fake,
        })
        self.client = self.app.test_client()
        self.store = JobStore(self.db)
        self.job_id = self.store.create("https://example.com/video.mp4", "caption", True)
        self.store.update(self.job_id, container_id="container-1", container_status="FINISHED")

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_rejects_missing_approval(self):
        response = self.client.post(f"/jobs/{self.job_id}/publish", data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake.publish_calls, 0)
        self.assertIsNone(self.store.get(self.job_id)["media_id"])

    def test_publish_rechecks_live_status(self):
        self.fake.status = "IN_PROGRESS"
        self.client.post(
            f"/jobs/{self.job_id}/publish",
            data={"approval": f"PUBLISH {self.job_id}", "confirmed": "on"},
        )
        self.assertEqual(self.fake.publish_calls, 0)

    def test_publish_succeeds_only_after_explicit_approval(self):
        self.client.post(
            f"/jobs/{self.job_id}/publish",
            data={"approval": f"PUBLISH {self.job_id}", "confirmed": "on"},
        )
        job = self.store.get(self.job_id)
        self.assertEqual(self.fake.publish_calls, 1)
        self.assertEqual(job["container_status"], "PUBLISHED")
        self.assertEqual(job["media_id"], "media-1")


if __name__ == "__main__":
    unittest.main()
