"""
Run once to get a Spotify refresh token and seed it into Upstash Redis.
Usage: python spotify_auth.py
Requires: pip install requests upstash-redis python-dotenv
"""
import os
import sys
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from base64 import b64encode

import requests
from dotenv import load_dotenv, find_dotenv
from upstash_redis import Redis

load_dotenv(find_dotenv())

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")

REDIRECT_URI = "http://127.0.0.1:8888/callback/"
SCOPES = "user-read-currently-playing user-read-recently-played"
REDIS_KEY = "spotify_refresh_token"

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            body = b"<h2>Authorization successful! You can close this tab.</h2>"
        else:
            error = params.get("error", ["unknown"])[0]
            body = f"<h2>Authorization failed: {error}</h2>".encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET in .env")
    if not KV_URL or not KV_TOKEN:
        sys.exit("Missing KV_REST_API_URL or KV_REST_API_TOKEN in .env")

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })

    print(f"Opening browser for Spotify authorization...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    print("Waiting for callback on http://127.0.0.1:8888/callback ...")
    server.handle_request()

    if not auth_code:
        sys.exit("No authorization code received.")

    # Exchange code for tokens
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={
            "Authorization": "Basic " + b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    data = response.json()
    if "refresh_token" not in data:
        sys.exit(f"Token exchange failed: {data}")

    refresh_token = data["refresh_token"]

    # Seed Redis
    r = Redis(url=KV_URL, token=KV_TOKEN)
    r.set(REDIS_KEY, refresh_token)

    print(f"\nDone! refresh_token seeded in Redis under key '{REDIS_KEY}'.")
    print("Your app will now rotate it automatically on each request.")


if __name__ == "__main__":
    main()
