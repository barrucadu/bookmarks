#!/usr/bin/env python3

from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConflictError, ConnectionError, NotFoundError
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    request,
)
from html2text import HTML2Text
from werkzeug.exceptions import HTTPException

import os
import requests

ES_INDEX = "bookmarks"

PAGE_SIZE = 50

BASE_URI = os.getenv("BASE_URI", "http://bookmarks.nyarlathotep")

app = Flask(__name__)
es = Elasticsearch([os.getenv("ES_HOST", "http://localhost:9200")])


def do_search(request_args):
    q = request_args.get("q")
    if q:
        query = {"query_string": {"query": q, "default_field": "content"}}
    else:
        query = {"match_all": {}}

    try:
        page = int(request_args.get("page"))
    except Exception:
        page = 0

    results = es.search(
        index=ES_INDEX,
        body={
            "query": {"bool": {"must": [query]}},
            "aggs": {"tags": {"terms": {"field": "tag", "size": 500}}},
            "from": page * PAGE_SIZE,
            "size": PAGE_SIZE,
        },
    )

    return {
        "tags": {
            d["key"]: d["doc_count"] for d in results["aggregations"]["tags"]["buckets"]
        },
        "results": [hit["_source"] for hit in results["hits"]["hits"]],
        "count": results["hits"]["total"]["value"],
        "page": page,
        "q": q,
    }


###############################################################################
## Response helpers


def accepts_html(request):
    return (
        (request.view_args or {}).get("fmt") in [None, "html"]
        and request.accept_mimetypes.accept_html
    )


def accepts_json(request):
    return (
        (request.view_args or {}).get("fmt") in [None, "json"]
        and request.accept_mimetypes.accept_json
    )


def fmt_http_error(request, code, message):
    if accepts_html(request):
        raise NotImplementedError()
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

    results = do_search(request.args)

    if accepts_html(request):
        raise NotImplementedError()
    else:
        return jsonify(results)


@app.route("/url", methods=["GET", "DELETE", "HEAD", "POST", "PUT"])
@app.route("/url.<fmt>", methods=["GET", "DELETE", "HEAD", "POST", "PUT"])
def bookmark_controller(**kwargs):
    url = request.args.get("url") or request.form.get("url")
    if not url:
        abort(400)

    if request.method in ["POST", "PUT"]:
        if not accepts_json(request):
            abort(406)

        title = request.args.get("title") or request.form.get("title")
        tags = request.args.getlist("tag") or request.form.getlist("tag")

        if not title:
            abort(400)

        # some websites (eg, rpg.net) block 'requests'
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0"
            },
        )
        r.raise_for_status()

        result = {
            "title": title,
            "url": url,
            "tag": tags,
            "indexed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "content": HTML2Text().handle(r.text),
        }

        try:
            es.create(index=ES_INDEX, id=url, body=result)
            return jsonify(result), 201
        except ConflictError:
            es.update(index=ES_INDEX, id=url, body={"doc": result})
            return jsonify(result), 200
    elif request.method == "DELETE":
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

@app.errorhandler(ConnectionError)
def handle_connection_error(*args):
    return fmt_http_error(
        request, 503, "The search server is unavailable.  Try again in a minute or two."
    )


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return fmt_http_error(request, e.code, e.description)


app.run(host="0.0.0.0", port=8888)
