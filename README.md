# 環境ロドリゲス Discord Bot

discord.py 製のBot。イベント管理・名簿/委員会・企画ロール・リマインド・グループ招待機能を搭載。

## セットアップ

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションを作成し、Botを追加してトークンを取得
   - Bot > Privileged Gateway Intents で `SERVER MEMBERS INTENT` と `MESSAGE CONTENT INTENT` を有効化
2. 依存パッケージをインストール

```
pip install -r requirements.txt
```

3. `.env.example` を `.env` にコピーし、`DISCORD_TOKEN` に取得したトークンを設定

```
cp .env.example .env
```

4. OAuth2 > URL Generator で `bot` と `applications.commands` スコープ、`Manage Channels`/`Manage Roles` 権限を選んで招待URLを発行し、サーバーに招待
5. Bot起動

```
python bot.py
```

## 機能

### イベント管理 ([cogs/events.py](cogs/events.py))
- `/イベント作成` — イベントを作成
- `/リマインド設定` — イベントにリマインドを設定（幹事・企画長のみ）
- `/イベント一覧` — 企画ごとのイベント一覧
- `/mtg` — MTGの出欠確認を投稿（幹事・企画長のみ）

### 委員会・グループ ([cogs/committee.py](cogs/committee.py))
- `/実行委員募集` — 実行委員の募集を開始（幹事・企画長のみ）
- `/グループ作成` — プライベートグループ（相談用スレッド）を作成
- `/グループ追加` — 現在のプライベートグループにメンバーを追加

### 企画ロール ([cogs/roles.py](cogs/roles.py))
- `/企画パネル設置` — 企画選択パネルを設置（幹事・企画長のみ）。ボタンで参加企画のロールを付与/解除

### リマインド ([cogs/reminders.py](cogs/reminders.py))
- `/remind when:<日時> content:<内容>` — リマインド登録（絶対指定 `2026/07/01 12:00`、相対指定 `1週間後` `3日後` `2時間後` など）
- `/reminders` — 自分のリマインド一覧
- `/remind_cancel reminder_id:<ID>` — キャンセル

### グループ招待 ([cogs/group_invite.py](cogs/group_invite.py))
- `/group_create target_channel:<対象チャンネル> emoji:<絵文字> description:<説明>` — 案内メッセージを投稿しグループを作成（要 `manage_roles` 権限）
- `/group_list` — 設定済みグループ一覧
- `/group_delete message_id:<ID>` — グループ削除
- リアクション追加で対象チャンネルの閲覧・送信権限を自動付与、リアクション削除で取り消し

## 構成

```
bot.py                 # エントリーポイント
cogs/
  events.py             # イベント管理
  committee.py          # 委員会・グループ
  roles.py              # 企画ロール
  reminders.py          # リマインド
  group_invite.py       # グループ招待
requirements.txt
.env.example
```
