# url2qr

[English](README.md) | [日本語](README-ja.md)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Author](https://img.shields.io/badge/author-Synge%20Todo-blue)](https://github.com/wistaria)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

URL を QR コード画像として保存する CLI ツールです。必要に応じて Bitly URL も生成できます。

Dropbox と Box 向けの追加スクリプトも含まれています。

Dropbox 用スクリプトはローカルの Dropbox パスから公開共有 URL を取得し、必要に応じて Bitly URL を作成して QR コードを生成します。

Box 用スクリプトも、ローカルの Box Drive フォルダに対して同じ処理を行います。

## 機能

- `BITLY_ACCESS_TOKEN` が設定されている場合、入力 URL から Bitly URL を生成
- QR コードを PNG 画像として出力
- QR コードに埋め込む URL を選択可能
  - `original` デフォルト: 元の URL
  - `short`: Bitly URL。Bitly が未設定の場合は元 URL または公開 URL
- ローカル Dropbox パスから公開 URL を生成し、QR コードを作成
- ローカル Box Drive フォルダから公開 URL を生成し、QR コードを作成

## 要件

- Python 3.10+
- Bitly Access Token: 任意。Bitly URL 生成に使用
- Dropbox Access Token: Dropbox パス workflow で使用
- Box OAuth 2.0 認証情報 — Client ID と Client Secret: Box パス workflow で使用

## セットアップ

スクリプトは初回実行時にシステムの一時ディレクトリへ仮想環境を作成し、`requirements.txt` から実行時依存関係を自動インストールします。macOS では `/private/tmp/$UID/url2qr` が使われます。

Bitly URL を使う場合は、Bitly token を環境変数に設定します。

```bash
export BITLY_ACCESS_TOKEN="your_bitly_token"
```

Dropbox workflow を使う場合は、Dropbox token も設定します。

```bash
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"
```

Box workflow を使う場合は、Box OAuth 2.0 の認証情報を設定します。

```bash
export BOX_CLIENT_ID="your_box_client_id"
export BOX_CLIENT_SECRET="your_box_client_secret"
```

初回実行時にブラウザが開き Box へのログインを求めます。認証後、トークンは
`~/.config/url2qr/box_tokens.json` にキャッシュされ、以降は自動更新されます。

## Bitly Access Token の取得方法

1. [bitly.com](https://bitly.com/) にサインインします。
2. アカウント設定ページを開きます。
3. developer/API セクションで access token を作成します。
4. token をコピーしてシェルに設定します。

```bash
export BITLY_ACCESS_TOKEN="your_bitly_token"
```

注: この token は秘密情報です。パスワードと同じように扱ってください。

## Dropbox Access Token の取得方法

1. [Dropbox App Console](https://www.dropbox.com/developers/apps) にサインインします。
2. 新しい app を作成します。Scoped access を推奨します。
3. 共有リンク用の権限を付与します。例: `sharing.write` と `sharing.read`
4. app 設定ページで access token を生成します。
5. シェルに設定します。

```bash
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"
```

## Box OAuth 2.0 のセットアップ

1. [Box Developer Console](https://app.box.com/developers/console) にサインインします。
2. **Custom App** → **User Authentication (OAuth 2.0)** で新しい app を作成します。
3. **Configuration → OAuth 2.0 Redirect URI** に `http://localhost:8080/callback` を追加します
   (`--redirect-port` を変更した場合はそのポートに合わせてください)。
4. **Configuration → Application Scopes** で以下を有効にします:
   - *Read all files and folders stored in Box*
   - *Write all files and folders stored in Box*
   - *Manage shared links*
5. Configuration タブから **Client ID** と **Client Secret** をコピーします。
6. シェルに設定します。

```bash
export BOX_CLIENT_ID="your_box_client_id"
export BOX_CLIENT_SECRET="your_box_client_secret"
```

初回実行時にブラウザで Box ログインを求められます。認可後、トークンは
`~/.config/url2qr/box_tokens.json` (パーミッション 600) に保存され、
以降はリフレッシュトークンで自動更新されます。

## 使い方

基本的な使い方:

```bash
python3 url2qr.py "https://example.com/some/very/long/url"
```

出力ファイルを指定:

```bash
python3 url2qr.py "https://example.com" -o myqr.png
```

`BITLY_ACCESS_TOKEN` が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
python3 url2qr.py "https://example.com" --qr-target short
```

コマンドは次の内容を表示します。

- 元 URL
- 生成された Bitly URL。Bitly が設定されている場合
- QR コード画像の出力先

Dropbox workflow:

```bash
python3 dropbox2qr.py "/Users/you/Library/CloudStorage/Dropbox/MyFolder/file.txt"
```

Dropbox API パスを直接渡すこともできます。

```bash
python3 dropbox2qr.py "/MyFolder/file.txt"
```

`BITLY_ACCESS_TOKEN` が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
python3 dropbox2qr.py "/MyFolder/file.txt" --qr-target short -o dropbox_qr.png
```

Box workflow:

```bash
python3 box2qr.py "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt"
```

Box API パスを直接渡すこともできます。

```bash
python3 box2qr.py "/MyFolder/file.txt"
```

`BITLY_ACCESS_TOKEN` が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
python3 box2qr.py "/MyFolder/file.txt" --qr-target short -o box_qr.png
```

## メモ

- `BITLY_ACCESS_TOKEN` が設定されている場合、Bitly API 呼び出しにネットワーク接続が必要です。
- 初回実行時の Python 依存関係インストールにもネットワーク接続が必要です。
- `BITLY_ACCESS_TOKEN` が未設定の場合、警告を表示し、Bitly URL 生成をスキップして QR コードだけを作成します。
- `URL2QR_NO_AUTO_VENV=1` を設定すると、自動仮想環境セットアップをスキップできます。

### Dropbox scope error のトラブルシューティング

`sharing.write` や `sharing.read` などの missing scope が表示される場合、Dropbox app token に十分な権限がありません。

1. Dropbox App Console を開き、対象 app を選択します。
2. 必要な scope を追加します: `sharing.write` と `sharing.read`
3. app 権限を保存します。
4. 新しい access token を生成します。古い token には新しい scope が自動反映されません。
5. 新しい token を export して、もう一度スクリプトを実行します。

### Box permission error のトラブルシューティング

Box の権限不足エラーが表示される場合:

1. [Box Developer Console](https://app.box.com/developers/console) を開き、対象 app を選択します。
2. **Configuration → Application Scopes** で *Read/Write files and folders* と *Manage shared links* を有効にします。
3. 変更を保存します。
4. キャッシュされたトークンを削除して、次回実行時に再認可させます:

   ```bash
   rm ~/.config/url2qr/box_tokens.json
   ```

5. もう一度 Box workflow を実行します — ブラウザが開いて再認可を求めます。
