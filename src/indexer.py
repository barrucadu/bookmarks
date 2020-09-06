#!/usr/bin/env python3

from bs4 import BeautifulSoup

import googleapiclient.discovery
import googleapiclient.errors

import functools
import os
import requests
import sys
import time

PATTERNS = {}

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


def default_scraper(url, soup=None):
    if soup is None:
        soup = download_page_html(url)
    return soup.text


def scraper(html, patterns):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(url):
            if html:
                soup = download_page_html(url)
            try:
                return func(url, soup) if html else func(url)
            except Exception as e:
                print(
                    f"falling back to html scraping for '{url}': {e}", file=sys.stderr
                )
                return default_scraper(url, soup=soup)

        for pattern in patterns:
            PATTERNS[pattern] = wrapper
        return wrapper

    return decorator


@scraper(html=True, patterns=["https://thealexandrian.net/wordpress/"])
def alexandrian_scraper(url, soup):
    entry_id = url.split("/")[4]
    return soup.find(id=f"post-{entry_id}").text


@scraper(html=True, patterns=["https://theangrygm.com/"])
def angrygm_scraper(url, soup):
    return soup.find_all("article")[0].text


@scraper(html=True, patterns=["https://www.artofmanliness.com/articles/"])
def artofmanliness_scraper(url, soup):
    header = soup.find_all(class_="post-title")[0]
    body = soup.find_all(class_="post-content-column")[0]
    for el in body.find_all("div"):
        el.clear()
    return header.text + "\n" + body.text


@scraper(html=True, patterns=["http://indie-rpgs.com/articles/"])
def forge_scraper(url, soup):
    title = soup.find_all(class_="maintitle")[1]
    body = soup.find_all(class_="gen")[2]
    nav_prev = body.find("td", align="left")
    nav_next = body.find("td", align="right")
    if nav_prev:
        nav_prev.clear()
    if nav_next:
        nav_next.clear()
    return title.text + "\n" + body.text.replace("\r", "\n")


@scraper(html=True, patterns=["http://goblinpunch.blogspot.com/"])
def goblinpunch_scraper(url, soup):
    return soup.find(class_="post-body").text


@scraper(html=False, patterns=["https://www.gov.uk/"])
def govuk_scraper(url):
    path = url.split("https://www.gov.uk")[1]
    try:
        search_data = download_page_json(
            "https://www.gov.uk/api/search.json",
            params={"filter_link": path, "fields": "title,indexable_content"},
        )
        result = search_data["results"][0]
        return result["title"] + "\n" + result["indexable_content"]
    except Exception as e:
        print(f"falling back to content-api for '{url}': {e}", file=sys.stderr)
        content_data = download_page_json(f"https://www.gov.uk/api/content{path}")
        body = content_data["details"]["body"]
        return BeautifulSoup(body, "html.parser").text


@scraper(html=True, patterns=["https://cheatsheetseries.owasp.org/cheatsheets/"])
def owasp_cheatsheets_scraper(url, soup):
    return soup.find_all("article")[0].text


@scraper(html=True, patterns=["https://reasonablypolymorphic.com/blog/"])
def reasonablypolymorphic_scraper(url, soup):
    return soup.find(class_="content").text


@scraper(
    html=False, patterns=["https://www.reddit.com/r/", "https://old.reddit.com/r/"]
)
def reddit_scraper(url):
    json = download_page_json(url + "/.json")
    return json[0]["data"]["children"][0]["data"]["selftext"]


@scraper(html=True, patterns=["https://blog.regehr.org/archives/"])
def regehr_scraper(url, soup):
    entry_id = url.split("/")[4]
    return soup.find(id=f"post-{entry_id}").text


@scraper(html=True, patterns=["https://en.wikipedia.org/wiki/"])
def wikipedia_scraper(url, soup):
    title = soup.find(id="firstHeading")
    body = soup.find(id="mw-content-text")
    for el, class_ in [
        ("div", "toc"),
        ("table", "metadata"),
        ("table", "vertical-navbox"),
        ("span", "mw-editsection"),
        ("div", "printfooter"),
    ]:
        for el in body.find_all(el, class_=class_):
            el.clear()
    return title.text + "\n" + body.text


@scraper(html=False, patterns=["https://www.youtube.com/watch?v="])
def youtube_scraper(url):
    video_id = url.split("v=")[1].split("&")[0]
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
    for pattern, scraper in PATTERNS.items():
        if url.startswith(pattern):
            return scraper(url)
    return default_scraper(url)


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
