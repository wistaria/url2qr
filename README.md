# url2qr

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Author](https://img.shields.io/badge/author-Synge%20Todo-blue)](https://github.com/wistaria)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A CLI tool that takes a URL, creates a Bitly short URL, and saves it as a QR code image.

It also includes additional scripts for Dropbox and Box workflows.

The Dropbox script takes a local Dropbox path, gets a public shared URL, and then creates a Bitly short URL and QR code.

The Box script does the same for local Box Drive folders.

## Features

- Generate a Bitly short URL from an input URL
- Export QR codes as PNG images
- Choose which URL to embed in the QR code
  - `original` (default): the original URL
  - `short`: the Bitly URL
- Generate a public Dropbox URL from a local Dropbox path, then create a short URL and QR code
- Generate a public Box URL from a local Box Drive folder, then create a short URL and QR code

## Requirements

- Python 3.10+
- Bitly Access Token
- Dropbox Access Token (for Dropbox path workflow)
- Box Access Token (for Box path workflow)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your Bitly token as an environment variable:

```bash
export BITLY_ACCESS_TOKEN="your_bitly_token"
```

If you use the Dropbox workflow, set your Dropbox token too:

```bash
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"
```

If you use the Box workflow, set your Box token too:

```bash
export BOX_ACCESS_TOKEN="your_box_token"
```

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

## How To Get A Box Access Token

1. Sign in to the [Box Developer Console](https://app.box.com/developers/console).
2. Create or open your Box app.
3. Enable the permissions required to read folders and manage shared links.
4. Generate a new access token for the app.
5. Export it in your shell:

```bash
export BOX_ACCESS_TOKEN="your_box_token"
```

## Usage

Quick start:

```bash
# 1) Activate virtual environment
source .venv/bin/activate

# 2) Set the required tokens
export BITLY_ACCESS_TOKEN="your_bitly_token"
export DROPBOX_ACCESS_TOKEN="your_dropbox_token"

# 3) Run the URL workflow
python url2qr.py "https://example.com/article/123" -o article_qr.png

# 4) Run the Dropbox workflow
python dropbox2qr.py "/MyFolder/file.txt" -o file_qr.png

# 5) Run the Box workflow
python box2qr.py "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt" -o box_qr.png
```

Basic usage:

```bash
python url2qr.py "https://example.com/some/very/long/url"
```

Specify an output file:

```bash
python url2qr.py "https://example.com" -o myqr.png
```

Embed the short URL in the QR code:

```bash
python url2qr.py "https://example.com" --qr-target short
```

The command prints:

- Original URL
- Generated short URL
- Output QR code file path

Dropbox workflow:

```bash
python dropbox2qr.py "/Users/you/Library/CloudStorage/Dropbox/MyFolder/file.txt"
```

Or pass a Dropbox API path directly:

```bash
python dropbox2qr.py "/MyFolder/file.txt"
```

Embed the short URL in the QR code:

```bash
python dropbox2qr.py "/MyFolder/file.txt" --qr-target short -o dropbox_qr.png
```

Box workflow:

```bash
python box2qr.py "/Users/you/Library/CloudStorage/Box/MyFolder/file.txt"
```

Or pass a Box API path directly:

```bash
python box2qr.py "/MyFolder/file.txt"
```

Embed the short URL in the QR code:

```bash
python box2qr.py "/MyFolder/file.txt" --qr-target short -o box_qr.png
```

## Testing

```bash
pytest -q
```

## Notes

- Network access is required to call the Bitly API.
- The command exits with an error if `BITLY_ACCESS_TOKEN` is not set.

### Dropbox scope error troubleshooting

If you see an error mentioning missing scopes such as `sharing.write` or `sharing.read`, your Dropbox app token does not have enough permissions.

1. Open Dropbox App Console and select your app.
2. Add required scopes: `sharing.write` and `sharing.read`.
3. Save app permissions.
4. Generate a new access token (old tokens do not automatically gain new scopes).
5. Export the new token and run the script again.

### Box permission error troubleshooting

If you see an error mentioning missing Box permissions, your Box app token does not have enough access.

1. Open the Box Developer Console and select your app.
2. Enable the permissions required for folders and shared links.
3. Save the changes.
4. Generate a new access token.
5. Export the new token and run the Box workflow again.
