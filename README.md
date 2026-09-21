# Instagram Reels 半自動投稿 MVP

最初の目的は、Instagram Login方式の公式APIでテスト用Business/CreatorアカウントへReelsを1本投稿することです。コンテナ作成と公開を別コマンドにし、公開には人間の明示承認文字列が必要です。

## 現行仕様（2026-09-21確認）

- APIホスト: `https://graph.instagram.com`
- APIバージョン: `v26.0`
- 権限: `instagram_business_basic`, `instagram_business_content_publish`
- 対象: Instagram Professional account（BusinessまたはCreator）
- 投稿: `POST /{ig_user_id}/media` → `GET /{container_id}?fields=status_code` → `POST /{ig_user_id}/media_publish`
- 公開動画URLはMetaの取得時に認証不要で到達可能であること
- AI生成動画ではコンテナ作成時に `is_ai_generated=true` を使用可能

## Meta側で最初に確認すること

1. Meta for DevelopersにBusinessタイプのアプリがある。
2. アプリにInstagram製品を追加し、`InstagramビジネスログインによるAPI設定`が表示される。
3. テスト用InstagramアカウントがBusinessまたはCreatorになっている。
4. API設定画面の対象アカウント横にある「トークンを生成」から長期トークンを取得できる。
5. 必要権限が `instagram_business_basic` と `instagram_business_content_publish` になっている。

自分のテスト用アカウントで開発モード検証する段階では、第三者向けOAuth画面やApp Reviewは後回しにします。トークンをチャット、Git、スクリーンショットへ貼らないでください。

## ローカル準備

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`.env` の `INSTAGRAM_ACCESS_TOKEN` にローカルでトークンを設定します。`INSTAGRAM_IG_USER_ID` は空でもよく、`GET /me` から解決します。

## 安全な検証順序

```powershell
# 1. 接続先アカウントを確認（投稿しない）
python cli.py whoami

# 2. URLがHTTPS・認証不要・video/*で返るか確認（投稿しない）
python cli.py check-url "https://example.com/test-vertical.mp4"

# 3. コンテナだけ作成（まだInstagram上には公開されない）
python cli.py create --video-url "https://example.com/test-vertical.mp4" --caption "API投稿テスト"

# 4. FINISHEDまで確認（まだ公開されない）
python cli.py status 1 --wait

# 5. 動画URL、caption、投稿先を再確認
python cli.py show 1

# 6. 明示承認して初めて公開
python cli.py publish 1 --approval "PUBLISH THIS REEL"
```

Veo動画では `create` に `--ai-generated` を付けます。最初の疎通確認は、自作した短い9:16 MP4で構いません。

## URL要件とStorage

GCSは必須ではありません。Metaが認証ヘッダーやCookieなしでHTTPS GETでき、リダイレクト後も動画を返し、処理完了までURLが失効しないStorage/CDNなら利用できます。署名URLは有効期限を十分長く取ります。Veoの出力URLは、そのまま使えると仮定せず `check-url` で検証します。

## 次の段階

初回投稿成功後に、トレンド候補収集、Gemini企画3案、Veo 9:16生成、Storage、ブラウザ承認画面、履歴・エラー保存、Scheduler/Actionsの順に拡張します。定期処理は公開直前で必ず停止し、人間承認後だけ `media_publish` を呼びます。
