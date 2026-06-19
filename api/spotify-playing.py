from flask import Flask, Response, render_template
from base64 import b64encode

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import requests
import os
import random
from upstash_redis import Redis

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET_ID = os.getenv("SPOTIFY_SECRET_ID")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

# scope user-read-currently-playing/user-read-recently-played
SPOTIFY_URL_REFRESH_TOKEN = "https://accounts.spotify.com/api/token"
SPOTIFY_URL_NOW_PLAYING = "https://api.spotify.com/v1/me/player/currently-playing"
SPOTIFY_URL_RECENTLY_PLAY = "https://api.spotify.com/v1/me/player/recently-played?limit=10"

REDIS_KEY = "spotify_refresh_token"

app = Flask(__name__)

_redis = None

def get_redis():
    global _redis
    if _redis is None:
        url = os.getenv("KV_REST_API_URL")
        token = os.getenv("KV_REST_API_TOKEN")
        if url and token:
            _redis = Redis(url=url, token=token)
    return _redis


def get_refresh_token():
    r = get_redis()
    if r:
        stored = r.get(REDIS_KEY)
        if stored:
            return stored
    return SPOTIFY_REFRESH_TOKEN


def getAuth():
    return b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET_ID}".encode()).decode("ascii")


def refreshToken():
    data = {
        "grant_type": "refresh_token",
        "refresh_token": get_refresh_token(),
    }

    headers = {"Authorization": "Basic {}".format(getAuth())}

    response = requests.post(SPOTIFY_URL_REFRESH_TOKEN, data=data, headers=headers)
    response_data = response.json()

    if response.status_code != 200 or "access_token" not in response_data:
        error = response_data.get("error", "unknown")
        raise Exception(f"Spotify token refresh failed ({error}): re-authorization required.")

    # Persist rotated refresh token so it never expires
    if "refresh_token" in response_data:
        r = get_redis()
        if r:
            r.set(REDIS_KEY, response_data["refresh_token"])

    return response_data["access_token"]

def recentlyPlayed():
    token = refreshToken()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(SPOTIFY_URL_RECENTLY_PLAY, headers=headers)

    if response.status_code == 204:
        return {}

    return response.json()

def nowPlaying():

    token = refreshToken()

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(SPOTIFY_URL_NOW_PLAYING, headers=headers)

    if response.status_code == 204:
        return {}

    return response.json()

def barGen(barCount):
    barCSS = ""
    left = 1
    for i in range(1, barCount + 1):
        anim = random.randint(1000, 1350)
        barCSS += ".bar:nth-child({})  {{ left: {}px; animation-duration: {}ms; }}".format(
            i, left, anim
        )
        left += 4

    return barCSS

def loadImageB64(url):
    resposne = requests.get(url)
    return b64encode(resposne.content).decode("ascii")

def makeSVG(data):
    barCount = 85
    contentBar = "".join(["<div class='bar'></div>" for i in range(barCount)])
    barCSS = barGen(barCount)

    if data == {}:
        content_bar = ""
        recent_plays = recentlyPlayed()
        size_recent_play = len(recent_plays["items"])
        idx = random.randint(0, size_recent_play - 1)
        item = recent_plays["items"][idx]["track"]
    else:
        item = data["item"]

    img = loadImageB64(item["album"]["images"][1]["url"])
    artistName = item["artists"][0]["name"].replace("&", "&amp;")
    songName = item["name"].replace("&", "&amp;")

    dataDict = {
        "content_bar": contentBar,
        "css_bar": barCSS,
        "artist_name": artistName,
        "song_name": songName,
        "img": img,
    }

    return render_template("spotify.html.j2", **dataDict)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):

    data = nowPlaying()
    svg = makeSVG(data)

    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "s-maxage=1"

    return resp

if __name__ == "__main__":
    app.run(debug=True)
