#!/usr/bin/env python3

from bs4 import BeautifulSoup

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


def requests_get(url, **kwargs):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, **kwargs)
    if r.status_code in [429, 503, 504]:
        time.sleep(TIMEOUT_BACKOFF_SECONDS)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, **kwargs)

    print(f"GET {url} => {r.status_code}", file=sys.stderr)
    if r.status_code == 200:
        return r
    return None


def download_page_html(url, **kwargs):
    return BeautifulSoup(requests_get(url, **kwargs).text, "html.parser")


def download_page_json(url, **kwargs):
    return requests_get(url, **kwargs).json()


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


def govuk_scraper(path):
    try:
        search_data = download_page_json(
            "https://www.gov.uk/api/search.json",
            params={"filter_link": path, "fields": "title,indexable_content"},
        )
        result = search_data["results"][0]
        return result["title"] + "\n" + result["indexable_content"]
    except Exception as e:
        print(f"falling back to content-api: {e}")
        content_data = download_page_json(f"https://www.gov.uk/api/content{path}")
        body = content_data["details"]["body"]
        return BeautifulSoup(body, "html.parser").text


def reasonablypolymorphic_scraper(soup):
    return soup.find(class_="content").text


def regehr_scraper(entry_id, soup):
    return soup.find(id=f"post-{entry_id}").text


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
            return alexandrian_scraper(url.split("/")[4], download_page_html(url))
        if url.startswith("https://theangrygm.com/"):
            return angrygm_scraper(download_page_html(url))
        if url.startswith("https://www.artofmanliness.com/articles/"):
            return artofmanliness_scraper(download_page_html(url))
        if url.startswith("http://goblinpunch.blogspot.com/"):
            return goblinpunch_scraper(download_page_html(url))
        if url.startswith("https://www.gov.uk/"):
            return govuk_scraper(url.split("https://www.gov.uk")[1])
        if url.startswith("https://reasonablypolymorphic.com/blog/"):
            return reasonablypolymorphic_scraper(download_page_html(url))
        if url.startswith("https://blog.regehr.org/archives/"):
            return regehr_scraper(url.split("/")[4], download_page_html(url))
        if url.startswith("https://en.wikipedia.org/wiki/"):
            return wikipedia_scraper(download_page_html(url))
        if url.startswith("https://www.youtube.com/watch?v="):
            return youtube_scraper(url.split("v=")[1].split("&")[0])
    except Exception as e:
        print(f"falling back to html scraping: {e}")
        return default_scraper(download_page_html(url))


def index_collection(urls):
    content = ""

    for u in urls:
        if len(content) >= MAX_CONTENT_FIELD_LEN:
            break
        content += ("\n" + (scrape_page_content(u) or "")).strip()

    return content[0:MAX_CONTENT_FIELD_LEN]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"USAGE: {sys.argv[0]} <url>...")
        sys.exit(1)

    urls = sys.argv[1:]
    print(index_collection(urls))
