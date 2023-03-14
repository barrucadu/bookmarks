#!/usr/bin/env python3

from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

import json
import os

ES_INDEX = "bookmarks"

es = Elasticsearch([os.getenv("ES_HOST", "http://localhost:9200")])
out = {}

for doc in scan(es, index=ES_INDEX):
    out[doc["_id"]] = doc["_source"]

print(json.dumps(out))
