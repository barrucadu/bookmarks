use elasticsearch::{Elasticsearch, Error};
use serde::{Deserialize, Serialize};

#[derive(Deserialize, Serialize)]
pub struct Record {}

pub async fn create(_client: &Elasticsearch) -> Result<(), Error> {
    println!("bookdb::index::create");
    Ok(())
}

pub async fn drop(_client: &Elasticsearch) -> Result<(), Error> {
    println!("bookdb::index::drop");
    Ok(())
}

pub async fn export(_client: &Elasticsearch) -> Result<Vec<Record>, Error> {
    println!("bookdb::index::export");
    Ok(Vec::new())
}

pub async fn import(
    _client: &Elasticsearch,
    _records: Vec<Record>,
) -> Result<Option<usize>, Error> {
    println!("bookdb::index::import");
    Ok(Some(0))
}
