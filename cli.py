from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from instagram_client import InstagramClient, InstagramConfig, validate_public_video_url
from store import JobStore


APPROVAL_PHRASE = "PUBLISH THIS REEL"


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Human-approved Instagram Reels MVP")
    parser.add_argument("--db", default=os.getenv("INSTAGRAM_DB", "instagram_mvp.db"))
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("whoami")

    check = commands.add_parser("check-url")
    check.add_argument("video_url")

    create = commands.add_parser("create")
    create.add_argument("--video-url", required=True)
    create.add_argument("--caption", required=True)
    create.add_argument("--ai-generated", action="store_true")

    status = commands.add_parser("status")
    status.add_argument("job_id", type=int)
    status.add_argument("--wait", action="store_true")

    show = commands.add_parser("show")
    show.add_argument("job_id", type=int)

    publish = commands.add_parser("publish")
    publish.add_argument("job_id", type=int)
    publish.add_argument("--approval", required=True)

    args = parser.parse_args()
    store = JobStore(args.db)

    if args.command == "check-url":
        print_json(validate_public_video_url(args.video_url))
        return
    if args.command == "show":
        print_json(store.get(args.job_id))
        return

    client = InstagramClient(InstagramConfig.from_env())
    if args.command == "whoami":
        print_json(client.get_profile())
        return
    if args.command == "create":
        url_info = validate_public_video_url(args.video_url)
        job_id = store.create(args.video_url, args.caption, args.ai_generated)
        container_id = client.create_reel_container(
            args.video_url, args.caption, is_ai_generated=args.ai_generated
        )
        store.update(job_id, container_id=container_id, container_status="IN_PROGRESS")
        print_json({"job_id": job_id, "container_id": container_id, "url_check": url_info})
        return
    if args.command == "status":
        job = store.get(args.job_id)
        if not job["container_id"]:
            raise SystemExit("Job has no container_id")
        state = (
            client.wait_until_finished(job["container_id"])
            if args.wait
            else client.get_container_status(job["container_id"])
        )
        store.update(args.job_id, container_status=state)
        print_json({"job_id": args.job_id, "status": state})
        return
    if args.command == "publish":
        job = store.get(args.job_id)
        print_json({
            "job_id": job["id"],
            "video_url": job["video_url"],
            "caption": job["caption"],
            "container_id": job["container_id"],
            "container_status": job["container_status"],
        })
        if args.approval != APPROVAL_PHRASE:
            raise SystemExit(f"Refusing to publish. Pass --approval '{APPROVAL_PHRASE}'")
        live_status = client.get_container_status(job["container_id"])
        if live_status != "FINISHED":
            raise SystemExit(f"Refusing to publish: live container status is {live_status}")
        media_id = client.publish_container(job["container_id"])
        media = client.get_media(media_id)
        store.update(
            args.job_id,
            approved_at=datetime.now(timezone.utc).isoformat(),
            container_status="PUBLISHED",
            media_id=media_id,
            permalink=media.get("permalink"),
            api_response_json=media,
        )
        print_json(media)


if __name__ == "__main__":
    main()

