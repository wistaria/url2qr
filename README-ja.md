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

- OAuth 2.0 または静的アクセストークンで Bitly URL を生成 (任意)
- QR コードを PNG 画像として出力
- QR コードに埋め込む URL を選択可能
  - `original` デフォルト: 元の URL
  - `short`: Bitly URL。Bitly が未設定の場合は元 URL または公開 URL
- ローカル Dropbox パスから公開 URL を生成し、QR コードを作成
- ローカル Box Drive フォルダから公開 URL を生成し、QR コードを作成

## 要件

- Python 3.10+
- Bitly 認証情報は任意です。初回利用時に入力できます
- Dropbox パス workflow では Dropbox 認証情報が必要です。初回利用時に入力できます
- Box パス workflow では Box OAuth 2.0 認証情報が必要です。初回利用時に入力できます

## セットアップ

スクリプトは初回実行時にシステムの一時ディレクトリへ仮想環境を作成し、`requirements.txt` から実行時依存関係を自動インストールします。macOS では `/private/tmp/$UID/url2qr` が使われます。

認証情報は環境変数から読みません。コマンドが不足している token または OAuth client 情報の
入力を求めた場合、`~/.config/url2qr` 配下にファイルモード 600 で保存します。
設定ディレクトリは可能な場合、モード 700 で作成します。

Bitly は任意です。デフォルトでは Bitly 認証情報を質問しません。Bitly token が未保存の状態で
Bitly を設定したい場合は `--bitly` を指定します。コマンドは静的 access token の入力を求めます。
空のまま Enter を押すと Bitly OAuth の設定に進み、`skip` と入力すると Bitly URL 生成を
スキップして QR コードだけを作成します。Bitly token が保存された後は、`--no-bitly` を
指定しない限り自動的に short URL を作成します。

Dropbox は静的 access token または OAuth 認証情報を利用できます。Dropbox token が
未保存の場合、まず静的 token の入力を求めます。空のまま Enter を押すと OAuth 設定に進みます。
OAuth token は `~/.config/url2qr/dropbox_tokens.json` に保存され、可能な場合は自動更新されます。

Box は OAuth 2.0 を使います。初回利用時に Box client ID と client secret の入力を求め、
ブラウザでログインしたあと、token を `~/.config/url2qr/box_tokens.json` に保存します。

## Bitly 静的アクセストークンの取得方法

1. [bitly.com](https://bitly.com/) にサインインします。
2. アカウント設定ページを開きます。
3. developer/API セクションで access token を作成します。
4. token をコピーし、コマンドが Bitly access token を求めたときに貼り付けます。

注: この token は秘密情報です。パスワードと同じように扱ってください。

## Bitly OAuth 2.0 のセットアップ

1. [Bitly](https://bitly.com/) にサインインし、**アカウント設定 → Integrations** を開きます。
2. 新しい OAuth アプリケーションを登録します。
3. **Redirect URIs** に `http://localhost:8080/callback` を追加します
   (`--redirect-port` を変更した場合はそのポートに合わせてください)。
4. **Client ID** と **Client Secret** をコピーします。
5. コマンドに `--bitly` を付けて実行し、Bitly access token の入力プロンプトでは空のまま Enter を押し、OAuth 認証情報を求められたら貼り付けます。

初回実行時にブラウザで Bitly ログインを求められます。認可後、OAuth 認証情報は
`~/.config/url2qr/bitly_credentials.json` (パーミッション 600) に保存され、
token は `~/.config/url2qr/bitly_tokens.json` (パーミッション 600) に保存されます。
以降は自動的に再利用されます。Bitly のトークンは失効しません。

## Dropbox 静的アクセストークンの取得方法

1. [Dropbox App Console](https://www.dropbox.com/developers/apps) にサインインします。
2. 新しい app を作成します。Scoped access を推奨します。
3. 共有リンク用の権限を付与します: `sharing.write` と `sharing.read`
4. app 設定ページで access token を生成します。
5. token をコピーし、コマンドが Dropbox access token を求めたときに貼り付けます。

## Dropbox OAuth 2.0 のセットアップ

1. [Dropbox App Console](https://www.dropbox.com/developers/apps) にサインインします。
2. **Scoped access** → **Full Dropbox** (または **App folder**) で新しい app を作成します。
3. **Permissions** で `sharing.write` と `sharing.read` を有効にします。
4. **Settings → OAuth 2 → Redirect URIs** に `http://localhost:8080/callback` を追加します
   (`--redirect-port` を変更した場合はそのポートに合わせてください)。
5. Settings タブから **App key** (Client ID) と **App secret** (Client Secret) をコピーします。
6. Dropbox access token の入力プロンプトでは空のまま Enter を押し、OAuth 認証情報を求められたら貼り付けます。

初回実行時にブラウザで Dropbox ログインを求められます。認可後、トークンは
`~/.config/url2qr/dropbox_credentials.json` (パーミッション 600) と
`~/.config/url2qr/dropbox_tokens.json` (パーミッション 600) に保存されます。
アクセストークンは4時間で失効し、リフレッシュトークンにより自動更新されます。

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
6. コマンドが Box OAuth 認証情報を求めたときに貼り付けます。

初回実行時にブラウザで Box ログインを求められます。認可後、トークンは
`~/.config/url2qr/box_credentials.json` (パーミッション 600) と
`~/.config/url2qr/box_tokens.json` (パーミッション 600) に保存され、
以降はリフレッシュトークンで自動更新されます。

### ブラウザのない環境 (ヘッドレス Linux 等)

`--no-browser` を渡すとローカル HTTP サーバーを起動しません。代わりに認可 URL が
表示されるので、任意のブラウザ (別マシンでも可) で開いて認可し、アドレスバーに表示される
コールバック URL をターミナルに貼り付けます。

```bash
./url2qr "https://example.com" --no-browser
# または
./dropbox2qr "/MyFolder/file.txt" --no-browser
# または
./box2qr "/MyFolder/file.txt" --no-browser
```

認可後、ブラウザは `http://localhost:8080/callback?code=...` にリダイレクトされます
(接続エラーが表示されますが正常です)。アドレスバーの URL 全体をコピーしてプロンプトに貼り付けてください。

注: `box2qr` の `--no-browser` は Bitly OAuth のみに作用します。Box OAuth はローカル
HTTP サーバーを使用するため、ヘッドレス環境では SSH ポートフォワーディングが必要です。

## 使い方

基本的な使い方:

```bash
./url2qr "https://example.com/some/very/long/url"
```

出力ファイルを指定:

```bash
./url2qr "https://example.com" -o myqr.png
```

Bitly が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
./url2qr "https://example.com" --qr-target short
```

初回利用時に Bitly を設定:

```bash
./url2qr "https://example.com" --bitly
```

Bitly をスキップして QR コードだけ生成 (Bitly token が保存済みでも無視):

```bash
./url2qr "https://example.com" --no-bitly
```

コマンドは次の内容を表示します。

- 元 URL
- 生成された Bitly URL (Bitly が設定されている場合)
- QR コード画像の出力先

Dropbox workflow:

```bash
./dropbox2qr "/Users/you/Library/CloudStorage/Dropbox/MyFolder/file.txt"
```

Dropbox API パスを直接渡すこともできます。

```bash
./dropbox2qr "/MyFolder/file.txt"
```

Bitly が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
./dropbox2qr "/MyFolder/file.txt" --qr-target short -o dropbox_qr.png
```

Box workflow:

```bash
./box2qr "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt"
```

Box API パスを直接渡すこともできます。

```bash
./box2qr "/MyFolder/file.txt"
```

Bitly が設定されている場合、Bitly URL を QR コードに埋め込みます。

```bash
./box2qr "/MyFolder/file.txt" --qr-target short -o box_qr.png
```

## メモ

- Bitly が設定されている場合、Bitly API 呼び出しにネットワーク接続が必要です。
- 初回実行時の Python 依存関係インストールにもネットワーク接続が必要です。
- Bitly が未設定の場合、Bitly URL 生成をスキップして QR コードだけを作成します。
- `--no-bitly` を指定すると、Bitly token が保存済みでも Bitly をスキップします。

### Dropbox scope error のトラブルシューティング

`sharing.write` や `sharing.read` などの missing scope が表示される場合、Dropbox app に十分な権限がありません。

1. Dropbox App Console を開き、対象 app を選択します。
2. **Permissions** で `sharing.write` と `sharing.read` を追加します。
3. app 権限を保存します。
4. 静的トークンを使用している場合: 新しい access token を生成します。古い token には新しい scope が自動反映されません。その後、キャッシュされた token を削除します。
5. OAuth 2.0 を使用している場合: キャッシュされた token を削除して、次回実行時に再認可させます:

   ```bash
   rm ~/.config/url2qr/dropbox_tokens.json
   ```

6. もう一度 Dropbox workflow を実行します。

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

### トークンキャッシュのリセット

各サービスを再認可するには、対応する token キャッシュファイルを削除します:

```bash
rm ~/.config/url2qr/bitly_tokens.json    # Bitly OAuth
rm ~/.config/url2qr/dropbox_tokens.json  # Dropbox OAuth
rm ~/.config/url2qr/box_tokens.json      # Box OAuth
```

次回実行時にブラウザが開きます (`--no-browser` の場合はコールバック URL の入力を求めます)。

保存済みの OAuth client 情報も消したい場合は、`~/.config/url2qr` 内の対応する
`*_credentials.json` ファイルを削除してください。
