#!/usr/bin/env python3

from common import es_presenter

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import RequestError

import os
import sys
import yaml

ES_INDEX = "bookmarks"

ES_CONFIG = {
    "mappings": {
        "properties": {
            "title": {
                "type": "text",
                "analyzer": "my_english",
            },
            "title_sort": {
                "type": "keyword",
            },
            "url": {
                "type": "keyword",
            },
            "domain": {
                "type": "keyword",
            },
            "tag": {
                "type": "keyword",
            },
            "indexed_at": {
                "type": "date",
            },
            "content": {
                "type": "text",
                "analyzer": "my_english",
            },
        },
    },
    "settings": {
        "analysis": {
            "filter": {
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_",
                },
                "custom_stems": {
                    "type": "stemmer_override",
                    "rules": [
                        # not "anim"
                        "anime => anime",
                        "animation => animation",
                        "animism => animism",
                        "animal, animals => animal",
                    ],
                },
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
                "english_possessive_stemmer": {
                    "type": "stemmer",
                    "language": "possessive_english",
                },
            },
            "analyzer": {
                "my_english": {
                    "tokenizer": "standard",
                    "filter": [
                        "english_possessive_stemmer",
                        "lowercase",
                        "english_stop",
                        "custom_stems",
                        "english_stemmer",
                    ],
                },
            },
        },
    },
}

es = Elasticsearch([os.getenv("ES_HOST", "http://localhost:9200")])
try:
    es.indices.create(index=ES_INDEX, **ES_CONFIG)
except RequestError:
    if os.getenv("DELETE_EXISTING_INDEX", "0") == "1":
        print("Index already exists - recreating it...")
        es.indices.delete(index=ES_INDEX)
        es.indices.create(index=ES_INDEX, **ES_CONFIG)
    else:
        print("Index already exists - set DELETE_EXISTING_INDEX=1 to recreate it")
        sys.exit(2)

if len(sys.argv) == 2:
    try:
        if sys.argv[1] == "-":
            dump = yaml.safe_load(sys.stdin)
        else:
            with open(sys.argv[1]) as f:
                dump = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Could not open data file {sys.argv[1]}")
        sys.exit(1)

    try:
        ok = 0
        errors = []
        for doc_id, doc in dump.items():
            try:
                es.create(index=ES_INDEX, id=doc_id, document=es_presenter(doc))
                ok += 1
            except Exception as e:
                errors.append(f"could not index {doc_id}: {e}")
        print(f"Indexed {ok} records")
        if errors:
            print("")
            for error in errors:
                print(error)
    except AttributeError:
        print(f"Expected {sys.argv[1]} to be an object")
        sys.exit(3)
