# url2qr

[English](README.md) | [日本語](README-ja.md)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Author](https://img.shields.io/badge/author-Synge%20Todo-blue)](https://github.com/wistaria)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A CLI tool that takes a URL and saves it as a QR code image, optionally creating a Bitly URL.

It also includes additional scripts for Dropbox and Box workflows.

The Dropbox script takes a local Dropbox path, gets a public shared URL, and then creates a QR code with an optional Bitly URL.

The Box script does the same for local Box Drive folders.

## Features

- Generate a Bitly URL via OAuth 2.0 or a static access token (optional)
- Export QR codes as PNG images
- Choose which URL to embed in the QR code
  - `original` (default): the original URL
  - `short`: the Bitly URL, or the original/public URL when Bitly is not configured
- Generate a public Dropbox URL from a local Dropbox path, then create a QR code
- Generate a public Box URL from a local Box Drive folder, then create a QR code

## Requirements

- Python 3.10+
- Bitly credentials are optional and can be entered on first use
- Dropbox credentials are required for the Dropbox path workflow and can be entered on first use
- Box OAuth 2.0 credentials are required for the Box path workflow and can be entered on first use

## Setup

The scripts create a virtual environment in the system temp directory and install runtime dependencies from `requirements.txt` automatically on first run. On macOS, the path is `/private/tmp/$UID/url2qr`.

Credentials are not read from environment variables. When a command prompts for
a missing token or OAuth client credentials, it saves them under `~/.config/url2qr`
with file mode 600. The config directory is created with mode 700 when possible.

Bitly is optional. By default, commands do not prompt for Bitly credentials. Pass
`--bitly` to configure Bitly when no Bitly token is cached. The command asks for
a static access token; leave it empty to configure Bitly OAuth, or type `skip` to
generate only the QR code. After a Bitly token is cached, commands create a short
URL automatically unless `--no-bitly` is specified.

Dropbox accepts either a static access token or OAuth credentials. If no Dropbox
token is cached, the command asks for a static token first; leave it empty to
configure OAuth. OAuth tokens are cached in `~/.config/url2qr/dropbox_tokens.json`
and refreshed automatically when possible.

Box uses OAuth 2.0. On first use, the command asks for the Box client ID and
client secret, opens a browser for login, then caches tokens in
`~/.config/url2qr/box_tokens.json`.

## How To Get A Bitly Static Access Token

1. Sign in to your Bitly account at [bitly.com](https://bitly.com/).
2. Open your account settings page.
3. Go to the developer/API section and create an access token.
4. Copy the token and paste it when the command prompts for a Bitly access token.

Note: Keep this token private. Treat it like a password.

## How To Set Up Bitly OAuth 2.0

1. Sign in to [Bitly](https://bitly.com/) and go to **Account Settings → Integrations**.
2. Register a new OAuth application.
3. Under **Redirect URIs**, add `http://localhost:8080/callback`
   (use a different port if you pass `--redirect-port`).
4. Copy the **Client ID** and **Client Secret**.
5. Run a command with `--bitly`, leave the Bitly access token prompt empty, and paste the OAuth credentials when prompted.

On the first run a browser window opens for Bitly login. After you authorize the app,
the OAuth credentials are saved to `~/.config/url2qr/bitly_credentials.json` (mode 600),
the token is saved to `~/.config/url2qr/bitly_tokens.json` (mode 600) and reused
automatically. Bitly tokens do not expire, so no refresh is needed.

## How To Get A Dropbox Static Access Token

1. Sign in to [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Create a new app (Scoped access recommended).
3. Grant permissions for sharing links: `sharing.write` and `sharing.read`.
4. Generate an access token in the app settings page.
5. Copy the token and paste it when the command prompts for a Dropbox access token.

## How To Set Up Dropbox OAuth 2.0

1. Sign in to [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Create a new app — choose **Scoped access** → **Full Dropbox** (or **App folder**).
3. Under **Permissions**, enable `sharing.write` and `sharing.read`.
4. Under **Settings → OAuth 2 → Redirect URIs**, add `http://localhost:8080/callback`
   (use a different port if you pass `--redirect-port`).
5. Copy the **App key** (Client ID) and **App secret** (Client Secret) from the Settings tab.
6. Leave the Dropbox access token prompt empty and paste the OAuth credentials when prompted.

On the first run a browser window opens for Dropbox login. After you authorize the app,
the OAuth credentials are saved to `~/.config/url2qr/dropbox_credentials.json` (mode 600), and
tokens are saved to `~/.config/url2qr/dropbox_tokens.json` (mode 600). The access token
expires after 4 hours and is refreshed automatically using the stored refresh token.

## How To Set Up Box OAuth 2.0

1. Sign in to the [Box Developer Console](https://app.box.com/developers/console).
2. Create a new app — choose **Custom App** → **User Authentication (OAuth 2.0)**.
3. Under **Configuration → OAuth 2.0 Redirect URI**, add `http://localhost:8080/callback`
   (use a different port if you pass `--redirect-port`).
4. Under **Configuration → Application Scopes**, enable at minimum:
   - *Read all files and folders stored in Box*
   - *Write all files and folders stored in Box*
   - *Manage shared links*
5. Copy the **Client ID** and **Client Secret** from the Configuration tab.
6. Paste them when the command prompts for Box OAuth credentials.

On the first run a browser window opens for Box login. After you authorize the app,
the OAuth credentials are saved to `~/.config/url2qr/box_credentials.json` (mode 600), and
tokens are saved to `~/.config/url2qr/box_tokens.json` (mode 600) and reused
automatically. The access token is refreshed silently using the stored refresh token.

### Headless or browser-less environments

Pass `--no-browser` to skip the local HTTP server. The script prints the authorization
URL and prompts you to paste the callback URL from your browser (which can be on a
different machine):

```bash
./url2qr "https://example.com" --no-browser
# or
./dropbox2qr "/MyFolder/file.txt" --no-browser
# or
./box2qr "/MyFolder/file.txt" --no-browser
```

After you open the printed URL in any browser and authorize, your browser will be
redirected to `http://localhost:8080/callback?code=...`. Copy that full URL from the
address bar and paste it at the prompt.

Note: For `box2qr`, `--no-browser` applies only to the Bitly OAuth step. Box OAuth
always uses the local HTTP server; use SSH port forwarding for headless Box authentication.

## Usage

Basic usage:

```bash
./url2qr "https://example.com/some/very/long/url"
```

Specify an output file:

```bash
./url2qr "https://example.com" -o myqr.png
```

Embed the Bitly URL in the QR code when Bitly is configured:

```bash
./url2qr "https://example.com" --qr-target short
```

Configure Bitly on first use:

```bash
./url2qr "https://example.com" --bitly
```

Skip Bitly even if a Bitly token is cached:

```bash
./url2qr "https://example.com" --no-bitly
```

The command prints:

- Original URL
- Generated Bitly URL, when Bitly is configured
- Output QR code file path

Dropbox workflow:

```bash
./dropbox2qr "/Users/you/Library/CloudStorage/Dropbox/MyFolder/file.txt"
```

Or pass a Dropbox API path directly:

```bash
./dropbox2qr "/MyFolder/file.txt"
```

Embed the Bitly URL in the QR code when Bitly is configured:

```bash
./dropbox2qr "/MyFolder/file.txt" --qr-target short -o dropbox_qr.png
```

Box workflow:

```bash
./box2qr "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt"
```

Or pass a Box API path directly:

```bash
./box2qr "/MyFolder/file.txt"
```

Embed the Bitly URL in the QR code when Bitly is configured:

```bash
./box2qr "/MyFolder/file.txt" --qr-target short -o box_qr.png
```

## Notes

- Network access is required to call the Bitly API when Bitly is configured.
- Network access is also required on first run to install Python dependencies.
- If Bitly is not configured, the command skips Bitly URL generation and still creates the QR code.
- `--no-bitly` skips Bitly even if a Bitly token is cached.

### Dropbox scope error troubleshooting

If you see an error mentioning missing scopes such as `sharing.write` or `sharing.read`, your Dropbox app does not have enough permissions.

1. Open Dropbox App Console and select your app.
2. Under **Permissions**, add `sharing.write` and `sharing.read`.
3. Save app permissions.
4. If using a static token: generate a new access token (old tokens do not automatically gain new scopes), then delete the cached token.
5. If using OAuth 2.0: delete the cached token so the next run re-authorizes with the new scopes:

   ```bash
   rm ~/.config/url2qr/dropbox_tokens.json
   ```

6. Run the Dropbox workflow again.

### Box permission error troubleshooting

If you see a permission or scope error when running the Box workflow:

1. Open the [Box Developer Console](https://app.box.com/developers/console) and select your app.
2. Under **Configuration → Application Scopes**, enable *Read/Write files and folders* and *Manage shared links*.
3. Save the changes.
4. Delete the cached tokens so the next run re-authorizes with the new scopes:

   ```bash
   rm ~/.config/url2qr/box_tokens.json
   ```

5. Run the Box workflow again — the browser will open for re-authorization.

### Token cache troubleshooting

To force re-authorization for any service, delete the corresponding token cache file:

```bash
rm ~/.config/url2qr/bitly_tokens.json    # Bitly OAuth
rm ~/.config/url2qr/dropbox_tokens.json  # Dropbox OAuth
rm ~/.config/url2qr/box_tokens.json      # Box OAuth
```

The next run will open a browser (or prompt for a callback URL with `--no-browser`) to re-authorize.

To forget stored OAuth client credentials as well, delete the corresponding
`*_credentials.json` file in `~/.config/url2qr`.
