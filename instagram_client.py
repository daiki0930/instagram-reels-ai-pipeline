from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests


class InstagramAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstagramConfig:
    access_token: str
    ig_user_id: str | None = None
    api_version: str = "v26.0"
    graph_host: str = "https://graph.instagram.com"

    @classmethod
    def from_env(cls) -> "InstagramConfig":
        token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
        if not token:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN is not set")
        return cls(
            access_token=token,
            ig_user_id=os.getenv("INSTAGRAM_IG_USER_ID", "").strip() or None,
            api_version=os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip(),
            graph_host=os.getenv(
                "INSTAGRAM_GRAPH_HOST", "https://graph.instagram.com"
            ).rstrip("/"),
        )


class InstagramClient:
    def __init__(self, config: InstagramConfig, timeout: int = 30):
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self.config.access_token}"}
        )

    def _url(self, path: str) -> str:
        return (
            f"{self.config.graph_host}/{self.config.api_version}/"
            f"{path.lstrip('/')}"
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(
            method, self._url(path), timeout=self.timeout, **kwargs
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramAPIError(
                f"Instagram returned HTTP {response.status_code} with non-JSON body"
            ) from exc
        if not response.ok or "error" in payload:
            error = payload.get("error", payload)
            message = error.get("message", "Unknown Instagram API error")
            code = error.get("code", response.status_code)
            subcode = error.get("error_subcode")
            detail = f"code={code}" + (f", subcode={subcode}" if subcode else "")
            raise InstagramAPIError(f"{message} ({detail})")
        return payload

    def get_profile(self) -> dict[str, Any]:
        return self._request(
            "GET",
            "me",
            params={"fields": "user_id,username,account_type"},
        )

    def resolve_ig_user_id(self) -> str:
        if self.config.ig_user_id:
            return self.config.ig_user_id
        payload = self.get_profile()
        rows = payload.get("data", [])
        if not rows or not rows[0].get("user_id"):
            raise InstagramAPIError("Could not resolve user_id from GET /me")
        return str(rows[0]["user_id"])

    def create_reel_container(
        self, video_url: str, caption: str, *, is_ai_generated: bool = False
    ) -> str:
        ig_user_id = self.resolve_ig_user_id()
        payload = self._request(
            "POST",
            f"{ig_user_id}/media",
            json={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "is_ai_generated": is_ai_generated,
            },
        )
        return str(payload["id"])

    def get_container_status(self, container_id: str) -> str:
        payload = self._request(
            "GET", container_id, params={"fields": "status_code,status"}
        )
        return str(payload.get("status_code", "UNKNOWN"))

    def wait_until_finished(
        self, container_id: str, *, interval_seconds: int = 15, timeout_seconds: int = 300
    ) -> str:
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self.get_container_status(container_id)
            if status == "FINISHED":
                return status
            if status in {"ERROR", "EXPIRED", "PUBLISHED"}:
                return status
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Container {container_id} did not finish within {timeout_seconds}s"
                )
            time.sleep(interval_seconds)

    def publish_container(self, container_id: str) -> str:
        ig_user_id = self.resolve_ig_user_id()
        payload = self._request(
            "POST",
            f"{ig_user_id}/media_publish",
            json={"creation_id": container_id},
        )
        return str(payload["id"])

    def get_media(self, media_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            media_id,
            params={
                "fields": "id,caption,media_type,media_product_type,permalink,timestamp"
            },
        )


def validate_public_video_url(url: str, timeout: int = 30) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError("video_url must use HTTPS")
    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        stream=True,
        headers={"Range": "bytes=0-1023"},
    )
    if response.status_code not in {200, 206}:
        raise ValueError(f"video_url returned HTTP {response.status_code}")
    content_type = response.headers.get("Content-Type", "")
    if not content_type.lower().startswith("video/"):
        raise ValueError(f"video_url Content-Type is not video/*: {content_type!r}")
    return {
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "content_length": response.headers.get("Content-Length"),
    }

