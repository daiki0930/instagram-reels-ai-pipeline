from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for

from instagram_client import InstagramAPIError, InstagramClient, InstagramConfig, validate_public_video_url
from store import JobStore


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.getenv("INSTAGRAM_DB", "instagram_mvp.db"),
    )
    if test_config:
        app.config.update(test_config)

    def store() -> JobStore:
        return JobStore(app.config["DATABASE"])

    def client() -> InstagramClient:
        factory = app.config.get("INSTAGRAM_CLIENT_FACTORY")
        if factory:
            return factory()
        return InstagramClient(InstagramConfig.from_env())

    @app.get("/")
    def index():
        return render_template("index.html", jobs=store().list_recent())

    @app.post("/jobs")
    def create_job():
        video_url = request.form.get("video_url", "").strip()
        caption = request.form.get("caption", "").strip()
        if not video_url or not caption:
            flash("動画URLとキャプションは必須です。", "error")
            return redirect(url_for("index"))
        job_id = store().create(
            video_url, caption, request.form.get("is_ai_generated") == "on"
        )
        flash(f"ジョブ #{job_id} を下書きとして保存しました。", "success")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.get("/jobs/<int:job_id>")
    def job_detail(job_id: int):
        return render_template("job.html", job=store().get(job_id))

    @app.post("/jobs/<int:job_id>/container")
    def create_container(job_id: int):
        job = store().get(job_id)
        if job["container_id"]:
            flash("このジョブには既にコンテナがあります。", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        try:
            validate_public_video_url(job["video_url"])
            container_id = client().create_reel_container(
                job["video_url"],
                job["caption"],
                is_ai_generated=bool(job["is_ai_generated"]),
            )
            store().update(
                job_id, container_id=container_id, container_status="IN_PROGRESS"
            )
            flash("Instagramの非公開コンテナを作成しました。", "success")
        except (ValueError, InstagramAPIError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.post("/jobs/<int:job_id>/refresh")
    def refresh_status(job_id: int):
        job = store().get(job_id)
        if not job["container_id"]:
            flash("先にコンテナを作成してください。", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        try:
            status = client().get_container_status(job["container_id"])
            store().update(job_id, container_status=status)
            flash(f"現在の状態: {status}", "success")
        except InstagramAPIError as exc:
            flash(str(exc), "error")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.post("/jobs/<int:job_id>/publish")
    def publish(job_id: int):
        job = store().get(job_id)
        expected = f"PUBLISH {job_id}"
        if request.form.get("approval", "") != expected:
            flash(f"公開には {expected} の入力が必要です。", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        if request.form.get("confirmed") != "on":
            flash("動画・キャプション・投稿先の確認チェックが必要です。", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        if not job["container_id"]:
            flash("公開可能なコンテナがありません。", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        try:
            api = client()
            live_status = api.get_container_status(job["container_id"])
            if live_status != "FINISHED":
                flash(f"公開を拒否しました。現在の状態: {live_status}", "error")
                return redirect(url_for("job_detail", job_id=job_id))
            media_id = api.publish_container(job["container_id"])
            media = api.get_media(media_id)
            store().update(
                job_id,
                approved_at=datetime.now(timezone.utc).isoformat(),
                container_status="PUBLISHED",
                media_id=media_id,
                permalink=media.get("permalink"),
                api_response_json=media,
            )
            flash("Reelを公開しました。", "success")
        except InstagramAPIError as exc:
            flash(str(exc), "error")
        return redirect(url_for("job_detail", job_id=job_id))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
