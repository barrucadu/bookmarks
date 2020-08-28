#!/usr/bin/env python3

from bs4 import BeautifulSoup
from datetime import datetime

import googleapiclient.discovery
import googleapiclient.errors

import os
import requests
import sys
import time

TIMEOUT_BACKOFF_SECONDS = 10

MAX_CONTENT_FIELD_LEN = 1000000

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# some websites (eg, rpg.net) block 'requests'
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0"
)


def download_page_content(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    if r.status_code in [429, 503, 504]:
        time.sleep(TIMEOUT_BACKOFF_SECONDS)
        r = requests.get(url, headers={"User-Agent": USER_AGENT})

    print(f"GET {url} => {r.status_code}", file=sys.stderr)
    if r.status_code != 200:
        return ""

    return BeautifulSoup(r.text, "html.parser")


def default_scraper(soup):
    return soup.text


def alexandrian_scraper(entry_id, soup):
    return soup.find(id=f"post-{entry_id}").text


def angrygm_scraper(soup):
    return soup.find_all("article")[0].text


def artofmanliness_scraper(soup):
    header = soup.find_all(class_="post-title")[0]
    body = soup.find_all(class_="post-content-column")[0]
    for el in body.find_all("div"):
        el.clear()
    return header.text + "\n" + body.text


def goblinpunch_scraper(soup):
    return soup.find(class_="post-body").text


def wikipedia_scraper(soup):
    return soup.find(id="content").text


def youtube_scraper(video_id):
    youtube = googleapiclient.discovery.build(
        "youtube", "v3", developerKey=YOUTUBE_API_KEY
    )
    request = youtube.videos().list(part="snippet,contentDetails", id=video_id)
    response = request.execute()["items"][0]["snippet"]
    return (
        response["title"]
        + "\n"
        + response["channelTitle"]
        + "\n"
        + response["description"]
    )


def scrape_page_content(url):
    try:
        if url.startswith("https://thealexandrian.net/wordpress/"):
            return alexandrian_scraper(url.split("/")[4], download_page_content(url))
        if url.startswith("https://theangrygm.com/"):
            return angrygm_scraper(download_page_content(url))
        if url.startswith("https://www.artofmanliness.com/articles/"):
            return artofmanliness_scraper(download_page_content(url))
        if url.startswith("http://goblinpunch.blogspot.com/"):
            return goblinpunch_scraper(download_page_content(url))
        if url.startswith("https://en.wikipedia.org/wiki/"):
            return wikipedia_scraper(download_page_content(url))
        if url.startswith("https://www.youtube.com/watch?v="):
            return youtube_scraper(url.split("v=")[1].split("&")[0])
    except Exception:
        return default_scraper(download_page_content(url))


def index_collection(titles, urls, tags=[], collection_title=None, content=None):
    if not titles:
        return None

    if len(titles) != len(urls):
        return None

    if len(titles) > 1:
        if collection_title:
            titles.insert(0, collection_title)
        else:
            return None

    if not content:
        content = ""
        for u in urls:
            if len(content) >= MAX_CONTENT_FIELD_LEN:
                break
            content += scrape_page_content(u) or ""
            content += "\n"
    content = content[0:MAX_CONTENT_FIELD_LEN]

    return {
        "title": titles if len(titles) > 1 else titles[0],
        "url": urls if len(urls) > 1 else urls[0],
        "tag": sorted([t.lower() for t in tags]),
        "indexed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "content": content,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"USAGE: {sys.argv[0]} <url>...")
        sys.exit(1)

    urls = sys.argv[1:]
    titles = ["." for u in urls]
    result = index_collection(titles, urls, collection_title=".")

    if result is None:
        print("An error occurred.")
        sys.exit(2)

    print(result["content"])
