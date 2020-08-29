from datetime import datetime


def current_time():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def es_presenter(source, reindex=False):
    indexed_at = source.get("indexed_at")
    if reindex or not indexed_at:
        indexed_at = current_time()

    return {
        "title": source["title"],
        "title_sort": source["title"][0]
        if type(source["title"]) is list
        else source["title"],
        "url": source["url"],
        "tag": sorted([t.lower() for t in source["tag"]]),
        "content": source["content"] or "",
        "indexed_at": indexed_at,
    }


def result_presenter(hit, highlight=False):
    out = {
        "title": hit["_source"]["title"],
        "url": hit["_source"]["url"],
        "tag": hit["_source"]["tag"],
        "indexed_at": hit["_source"]["indexed_at"],
    }

    # Coerce between singleton lists and individual values: ES smushes
    # a singleton list into a single value, so it's convenient to do
    # the same even if this function receives a hit constructed in
    # Python rather than fetched from ES.
    if type(out["title"]) is list and len(out["title"]) == 1:
        out["title"] = out["title"][0]
    if type(out["url"]) is list and len(out["url"]) == 1:
        out["url"] = out["url"][0]
    if type(out["tag"]) is not list:
        out["tag"] = [out["tag"]]
    if type(out["indexed_at"]) is list:
        out["indexed_at"] = out["indexed_at"][0]

    primary_url = out["url"]
    if type(out["url"]) is list:
        primary_url = out["url"][0]
        out["parts"] = [
            {"url": out["url"][i], "title": out["title"][i + 1]}
            for i in range(len(out["url"]))
        ]
        out["title"] = out["title"][0]
        del out["url"]

    try:
        out["domain"] = primary_url.split("/")[2]
    except IndexError:
        out["domain"] = primary_url

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
