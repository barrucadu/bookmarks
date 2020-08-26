#!/usr/bin/env python3

from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConflictError, ConnectionError, NotFoundError
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from html2text import HTML2Text
from urllib.parse import quote_plus
from werkzeug.exceptions import HTTPException

import math
import os
import requests

ES_INDEX = "bookmarks"

PAGE_SIZE = 20

BASE_URI = os.getenv("BASE_URI", "http://bookmarks.nyarlathotep")

ALLOW_WRITES = os.getenv("ALLOW_WRITES", "0") == "1"

app = Flask(__name__)
app.jinja_env.filters["quote_plus"] = lambda u: quote_plus(u)

es = Elasticsearch([os.getenv("ES_HOST", "http://localhost:9200")])


def sanitize(html):
    h = HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_emphasis = True
    h.ignore_tables = True
    return h.handle(html)


def transform_hit(hit, highlight):
    out = hit["_source"]
    if highlight:
        try:
            fragment = hit["highlight"]["content"][0]
            if fragment:
                unhighlighted_fragment = fragment.replace("<mark>", "").replace(
                    "</mark>", ""
                )
                if not hit["_source"]["content"].startswith(unhighlighted_fragment):
                    fragment = "…" + fragment
                if not hit["_source"]["content"].endswith(unhighlighted_fragment):
                    fragment += "…"
                out["fragment"] = fragment
        except KeyError:
            pass
    return out


def all_tags():
    results = es.search(
        index=ES_INDEX,
        body={
            "query": {"bool": {"must": [{"match_all": {}}]}},
            "aggs": {"tags": {"terms": {"field": "tag", "size": 500}}},
        },
    )

    return {
        d["key"]: d["doc_count"] for d in results["aggregations"]["tags"]["buckets"]
    }


def do_search(request_args, highlight=False):
    q = request_args.get("q", "")
    if q:
        query = {"query_string": {"query": q, "default_field": "content"}}
    else:
        query = {"match_all": {}}

    try:
        page = int(request_args.get("page")) - 1
    except Exception:
        page = 0

    body = {
        "query": {"bool": {"must": [query]}},
        "aggs": {"tags": {"terms": {"field": "tag", "size": 500}}},
        "from": page * PAGE_SIZE,
        "size": PAGE_SIZE,
        "sort": ["_score", "title_sort"],
    }
    if highlight:
        body["highlight"] = {
            "fields": {"content": {}},
            "fragment_size": 300,
            "pre_tags": "<mark>",
            "post_tags": "</mark>",
        }

    results = es.search(index=ES_INDEX, body=body)

    count = results["hits"]["total"]["value"]
    return {
        "tags": {
            d["key"]: d["doc_count"] for d in results["aggregations"]["tags"]["buckets"]
        },
        "results": [transform_hit(hit, highlight) for hit in results["hits"]["hits"]],
        "count": count,
        "page": page + 1,
        "pages": math.ceil(count / PAGE_SIZE),
        "q": q,
    }


###############################################################################
## Response helpers


def accepts_html(request):
    return (request.view_args or {}).get("fmt") in [
        None,
        "html",
    ] and request.accept_mimetypes.accept_html


def accepts_json(request):
    return (request.view_args or {}).get("fmt") in [
        None,
        "json",
    ] and request.accept_mimetypes.accept_json


def fmt_http_error(request, code, message):
    if accepts_html(request):
        return (
            render_template(
                "error.html", code=code, message=message, base_uri=BASE_URI
            ),
            code,
        )
    else:
        return jsonify({"code": code, "message": message}), code


###############################################################################
## Controllers


@app.route("/")
def redirect_to_search():
    return redirect(f"{BASE_URI}/search", code=301)


@app.route("/search")
@app.route("/search.<fmt>")
def search(**kwargs):
    if not accepts_html(request) and not accepts_json(request):
        abort(406)

    if accepts_html(request):
        results = do_search(request.args, highlight=True)
        return render_template(
            "search.html", allow_writes=ALLOW_WRITES, base_uri=BASE_URI, **results
        )
    else:
        results = do_search(request.args)
        return jsonify(results)


@app.route("/add")
@app.route("/add.<fmt>")
def add_bookmark(**kwargs):
    if not ALLOW_WRITES:
        abort(403)

    if not accepts_html(request):
        abort(406)

    return render_template(
        "add.html", base_uri=BASE_URI, all_tags=list(all_tags().keys())
    )


@app.route("/url", methods=["GET", "DELETE", "HEAD", "POST", "PUT"])
@app.route("/url.<fmt>", methods=["GET", "DELETE", "HEAD", "POST", "PUT"])
def bookmark_controller(**kwargs):
    url = request.args.get("url") or request.form.get("url")
    if not url:
        abort(400)

    if request.method in ["POST", "PUT"]:
        if not ALLOW_WRITES:
            abort(403)

        if not accepts_html(request) and not accepts_json(request):
            abort(406)

        title = request.args.get("title") or request.form.get("title")
        tags = request.args.getlist("tag") or request.form.getlist("tag")
        content = request.args.get("content") or request.form.get("content")

        if not title:
            abort(400)

        if not content:
            # some websites (eg, rpg.net) block 'requests'
            r = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0"
                },
            )
            r.raise_for_status()
            content = sanitize(r.text)

        result = {
            "title": title.strip(),
            "url": url.strip(),
            "tag": sorted([t.strip().lower() for t in tags if t.strip()]),
            "indexed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "content": content,
        }

        code = 201
        try:
            es.create(index=ES_INDEX, id=url, body=result)
        except ConflictError:
            es.update(index=ES_INDEX, id=url, body={"doc": result})
            code = 200
        if accepts_html(request):
            return (
                render_template("post-add.html", base_uri=BASE_URI, result=result),
                code,
            )
        else:
            return jsonify(result), code
    elif request.method == "DELETE":
        if not ALLOW_WRITES:
            abort(403)

        try:
            es.delete(index=ES_INDEX, id=url)
        except NotFoundError:
            pass
        return "", 204
    else:
        try:
            result = es.get(index=ES_INDEX, id=url)
            if accepts_json(request):
                return jsonify(result)
            else:
                abort(406)
        except NotFoundError:
            abort(404)


@app.route("/static/<path>")
def static_files(path):
    return send_from_directory("static", path)


@app.errorhandler(ConnectionError)
def handle_connection_error(*args):
    return fmt_http_error(
        request, 503, "The search server is unavailable.  Try again in a minute or two."
    )


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return fmt_http_error(request, e.code, e.description)


app.run(host="0.0.0.0", port=8888)
