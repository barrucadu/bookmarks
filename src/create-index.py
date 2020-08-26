#!/usr/bin/env python3

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import RequestError

import os
import sys
import yaml

ES_INDEX = "bookmarks"

try:
    with open("config/elasticsearch-schema.yaml") as f:
        es_config = yaml.safe_load(f)
except FileNotFoundError:
    print("Could not read config/elasticsearch-schema.yaml")
    sys.exit(1)

es = Elasticsearch([os.getenv("ES_HOST", "http://localhost:9200")])
try:
    es.indices.create(index=ES_INDEX, body=es_config)
except RequestError:
    if os.getenv("DELETE_EXISTING_INDEX", "0") == "1":
        print("Index already exists - recreating it...")
        es.indices.delete(index=ES_INDEX)
        es.indices.create(index=ES_INDEX, body=es_config)
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
                es.create(index=ES_INDEX, id=doc_id, body=doc)
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
