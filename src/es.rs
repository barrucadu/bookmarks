use elasticsearch::http::request::JsonBody;
use elasticsearch::indices::{IndicesCreateParts, IndicesDeleteParts};
use elasticsearch::{BulkParts, ClearScrollParts, Elasticsearch, Error, ScrollParts, SearchParts};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::string::ToString;

static INDEX_NAME: &str = "bookmarks";

#[derive(Deserialize, Serialize)]
pub struct Record {
    pub title: Vec<String>,
    pub title_sort: String,
    pub url: Vec<String>,
    pub domain: String,
    pub tag: Vec<String>,
    pub content: String,
}

impl Record {
    fn id(&self) -> String {
        self.url[0].clone()
    }
}

pub async fn create(client: &Elasticsearch) -> Result<(), Error> {
    client
        .indices()
        .create(IndicesCreateParts::Index(INDEX_NAME))
        .body(json!({
            "mappings": {
                "properties": {
                    "title": { "type": "text", "analyzer": "my_english" },
                    "title_sort": { "type": "keyword" },
                    "url": { "type": "keyword" },
                    "domain": { "type": "keyword" },
                    "tag": { "type": "keyword" },
                    "content": { "type": "text", "analyzer": "my_english" },
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
        }))
        .send()
        .await
        .map(|_| ())
}

pub async fn drop(client: &Elasticsearch) -> Result<(), Error> {
    client
        .indices()
        .delete(IndicesDeleteParts::Index(&[INDEX_NAME]))
        .send()
        .await
        .map(|_| ())
}

pub async fn export(client: &Elasticsearch) -> Result<Vec<Record>, Error> {
    let mut records = Vec::new();

    let mut response = client
        .search(SearchParts::Index(&[INDEX_NAME]))
        .scroll("5m")
        .body(json!({"query": {"match_all": {}}, "sort": ["title_sort"]}))
        .send()
        .await?;
    let mut response_body = response.json::<Value>().await?;
    let mut scroll_id = response_body["_scroll_id"].as_str().unwrap();
    let mut hits = response_body["hits"]["hits"].as_array().unwrap();

    while !hits.is_empty() {
        records.extend(
            hits.iter()
                .map(|hit| Record::deserialize(&hit["_source"]).unwrap()),
        );
        response = client
            .scroll(ScrollParts::ScrollId(scroll_id))
            .scroll("5m")
            .send()
            .await?;
        response_body = response.json::<Value>().await?;
        scroll_id = response_body["_scroll_id"].as_str().unwrap();
        hits = response_body["hits"]["hits"].as_array().unwrap();
    }

    client
        .clear_scroll(ClearScrollParts::ScrollId(&[scroll_id]))
        .send()
        .await?;

    Ok(records)
}

pub async fn import(client: &Elasticsearch, records: Vec<Record>) -> Result<Option<usize>, Error> {
    let mut body: Vec<JsonBody<_>> = Vec::with_capacity(records.len() * 2);
    for record in &records {
        body.push(json!({"index": {"_id": record.id()}}).into());
        body.push(serde_json::to_value(record).unwrap().into());
    }

    let response = client
        .bulk(BulkParts::Index(INDEX_NAME))
        .body(body)
        .send()
        .await?;
    let response_body = response.json::<Value>().await?;
    if response_body["errors"].as_bool().unwrap() {
        Ok(None)
    } else {
        Ok(Some(records.len()))
    }
}

///////////////////////////////////////////////////////////////////////////////

static PAGE_SIZE: u64 = 25;

pub struct SearchResult {
    pub domains: HashMap<String, u64>,
    pub tags: HashMap<String, u64>,
    pub results: Vec<(Record, Option<String>)>,
    pub total: u64,
    pub page: u64,
    pub pages: u64,
}

pub async fn search(
    client: &Elasticsearch,
    query: &Option<&str>,
    page: u64,
) -> Result<SearchResult, Error> {
    let query = match query {
        Some(q) => json!({"query_string": {"query": q, "default_field": "content"}}),
        None => json!({"match_all": {}}),
    };
    let body = json!({
        "query": query,
        "aggs": {
            "domains": {"terms": {"field": "domain", "size": 500}},
            "tags": {"terms": {"field": "tag", "size": 500}},
        },
        "highlight": {
            "fields": {"content": {}},
            "fragment_size": 300,
            "pre_tags": "<mark>",
            "post_tags": "</mark>",
        },
        "from": (page - 1) * PAGE_SIZE,
        "size": PAGE_SIZE,
        "sort": ["_score", "title_sort"],
    });

    let response = client
        .search(SearchParts::Index(&[INDEX_NAME]))
        .body(body)
        .send()
        .await?;
    let response_body = response.json::<Value>().await?;
    let hits = response_body["hits"]["hits"].as_array().unwrap();
    let results = hits.iter().map(present_hit).collect();
    let aggs = response_body["aggregations"].clone();
    let total = response_body["hits"]["total"]["value"].as_u64().unwrap();

    Ok(SearchResult {
        domains: agg_buckets_to_hashmap(&aggs["domains"]["buckets"]),
        tags: agg_buckets_to_hashmap(&aggs["tags"]["buckets"]),
        results,
        total,
        page,
        pages: f64::ceil(total as f64 / PAGE_SIZE as f64) as u64,
    })
}

pub async fn list_tags(client: &Elasticsearch) -> Result<Vec<String>, Error> {
    let body = json!({
        "_source": false,
        "query": {"match_all": {}},
        "aggs": {"tags": {"terms": {"field": "tag", "size": 500}}},
    });

    let response = client
        .search(SearchParts::Index(&[INDEX_NAME]))
        .body(body)
        .send()
        .await?;
    let response_body = response.json::<Value>().await?;

    let mut tags: Vec<_> = response_body["aggregations"]["tags"]["buckets"]
        .as_array()
        .unwrap()
        .iter()
        .map(|b| b["key"].as_str().unwrap().to_string())
        .collect();
    tags.sort();

    Ok(tags)
}

fn present_hit(hit: &Value) -> (Record, Option<String>) {
    let record = Record::deserialize(&hit["_source"]).unwrap();
    let highlight = hit["highlight"]["content"][0]
        .as_str()
        .map(ToString::to_string);

    (record, highlight)
}

fn agg_buckets_to_hashmap(buckets: &Value) -> HashMap<String, u64> {
    if let Some(buckets) = buckets.as_array() {
        let mut out = HashMap::with_capacity(buckets.len());
        for bucket in buckets {
            let key = bucket["key"].as_str().unwrap().to_string();
            let doc_count = bucket["doc_count"].as_u64().unwrap();
            out.insert(key, doc_count);
        }
        out
    } else {
        HashMap::new()
    }
}
