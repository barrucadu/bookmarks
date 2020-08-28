#!/usr/bin/env python3

from bs4 import BeautifulSoup
from datetime import datetime

import requests
import sys
import time

TIMEOUT_BACKOFF_SECONDS = 10

MAX_CONTENT_FIELD_LEN = 1000000

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
    body = soup.find(id=f"post-{entry_id}")
    if body:
        return body.text

    return default_scraper(soup)


def angrygm_scraper(soup):
    articles = soup.find_all("article")
    if articles and articles[0]:
        return articles[0].text

    return default_scraper(soup)


def goblinpunch_scraper(soup):
    body = soup.find(class_="post-body")
    if body:
        return body.text

    return default_scraper(soup)


def wikipedia_scraper(soup):
    body = soup.find(id="content")
    if body:
        return body.text

    return default_scraper(soup)


def scraper_for_url(url):
    bits = url.split("/")
    if url.startswith("https://thealexandrian.net/wordpress/") and len(bits) >= 5:
        return lambda soup: alexandrian_scraper(bits[4], soup)
    if url.startswith("https://theangrygm.com/"):
        return angrygm_scraper
    if url.startswith("http://goblinpunch.blogspot.com/"):
        return goblinpunch_scraper
    if url.startswith("https://en.wikipedia.org/wiki/"):
        return wikipedia_scraper

    return default_scraper


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
            content += scraper_for_url(u)(download_page_content(u))
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
