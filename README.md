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

- Generate a Bitly URL from an input URL when `BITLY_ACCESS_TOKEN` is set
- Export QR codes as PNG images
- Choose which URL to embed in the QR code
  - `original` (default): the original URL
  - `short`: the Bitly URL, or the original/public URL when Bitly is not configured
- Generate a public Dropbox URL from a local Dropbox path, then create a QR code
- Generate a public Box URL from a local Box Drive folder, then create a QR code

## Requirements

- Python 3.10+
- Bitly Access Token (optional; enables Bitly URLs)
- Dropbox Access Token (for Dropbox path workflow)
- Box OAuth 2.0 credentials — Client ID and Client Secret (for Box path workflow)

## Setup

The scripts create a virtual environment in the system temp directory and install runtime dependencies from `requirements.txt` automatically on first run. On macOS, the path is `/private/tmp/$UID/url2qr`.

Set your Bitly token as an environment variable if you want Bitly URLs:

```bash
export BITLY_ACCESS_TOKEN="your_bitly_token"
```

If you use the Dropbox workflow, set your Dropbox token too:

```bash
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"
```

If you use the Box workflow, set your Box OAuth 2.0 credentials:

```bash
export BOX_CLIENT_ID="your_box_client_id"
export BOX_CLIENT_SECRET="your_box_client_secret"
```

On first run the script opens a browser for Box login. Tokens are cached in
`~/.config/url2qr/box_tokens.json` and refreshed automatically afterwards.

## How To Get A Bitly Access Token

1. Sign in to your Bitly account at [bitly.com](https://bitly.com/).
2. Open your account settings page.
3. Go to the developer/API section and create an access token.
4. Copy the token and set it in your shell:

```bash
export BITLY_ACCESS_TOKEN="your_bitly_token"
```

Note: Keep this token private. Treat it like a password.

## How To Get A Dropbox Access Token

1. Sign in to [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Create a new app (Scoped access recommended).
3. Grant permissions for sharing links (for example, `sharing.write` and `sharing.read`).
4. Generate an access token in the app settings page.
5. Set it in your shell:

```bash
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"
```

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
6. Set them in your shell:

```bash
export BOX_CLIENT_ID="your_box_client_id"
export BOX_CLIENT_SECRET="your_box_client_secret"
```

On the first run a browser window opens for Box login. After you authorize the app,
tokens are saved to `~/.config/url2qr/box_tokens.json` (mode 600) and reused
automatically. The access token is refreshed silently using the stored refresh token.

## Usage

Basic usage:

```bash
python3 url2qr.py "https://example.com/some/very/long/url"
```

Specify an output file:

```bash
python3 url2qr.py "https://example.com" -o myqr.png
```

Embed the Bitly URL in the QR code when `BITLY_ACCESS_TOKEN` is set:

```bash
python3 url2qr.py "https://example.com" --qr-target short
```

The command prints:

- Original URL
- Generated Bitly URL, when Bitly is configured
- Output QR code file path

Dropbox workflow:

```bash
python3 dropbox2qr.py "/Users/you/Library/CloudStorage/Dropbox/MyFolder/file.txt"
```

Or pass a Dropbox API path directly:

```bash
python3 dropbox2qr.py "/MyFolder/file.txt"
```

Embed the Bitly URL in the QR code when `BITLY_ACCESS_TOKEN` is set:

```bash
python3 dropbox2qr.py "/MyFolder/file.txt" --qr-target short -o dropbox_qr.png
```

Box workflow:

```bash
python3 box2qr.py "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt"
```

Or pass a Box API path directly:

```bash
python3 box2qr.py "/MyFolder/file.txt"
```

Embed the Bitly URL in the QR code when `BITLY_ACCESS_TOKEN` is set:

```bash
python3 box2qr.py "/MyFolder/file.txt" --qr-target short -o box_qr.png
```

## Notes

- Network access is required to call the Bitly API when `BITLY_ACCESS_TOKEN` is set.
- Network access is also required on first run to install Python dependencies.
- If `BITLY_ACCESS_TOKEN` is not set, the command prints a warning, skips Bitly URL generation, and still creates the QR code.
- Set `URL2QR_NO_AUTO_VENV=1` to skip automatic virtual environment setup.

### Dropbox scope error troubleshooting

If you see an error mentioning missing scopes such as `sharing.write` or `sharing.read`, your Dropbox app token does not have enough permissions.

1. Open Dropbox App Console and select your app.
2. Add required scopes: `sharing.write` and `sharing.read`.
3. Save app permissions.
4. Generate a new access token (old tokens do not automatically gain new scopes).
5. Export the new token and run the script again.

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
