use elasticsearch::http::request::JsonBody;
use elasticsearch::indices::{IndicesCreateParts, IndicesDeleteParts};
use elasticsearch::{BulkParts, ClearScrollParts, Elasticsearch, Error, ScrollParts, SearchParts};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

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
