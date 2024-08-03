use axum::body::Body;
use axum::extract::{Multipart, Query, State};
use axum::http::header;
use axum::http::StatusCode;
use axum::response::{Html, IntoResponse, Redirect, Response};
use axum::{routing, Router};
use elasticsearch::http::transport::Transport;
use elasticsearch::Elasticsearch;
use lazy_static::lazy_static;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::net::SocketAddr;
use tera::Tera;

use crate::es;

pub async fn serve(
    es_host: String,
    address: SocketAddr,
    allow_writes: bool,
) -> std::io::Result<()> {
    let app_state = AppState {
        es_host,
        allow_writes,
    };

    let app = routes(allow_writes)
        .fallback(fallback_404)
        .with_state(app_state);
    let listener = tokio::net::TcpListener::bind(address).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

fn routes(allow_writes: bool) -> Router<AppState> {
    let ro_app = Router::new()
        .route("/", routing::get(get_index))
        .route("/search", routing::get(get_search))
        .route(
            "/resources/style.css",
            routing::get(get_resource_stylesheet),
        )
        .route(
            "/resources/search.svg",
            routing::get(get_resource_searchsvg),
        )
        .route(
            "/resources/fira-mono.woff2",
            routing::get(get_resource_firamono),
        )
        .route(
            "/resources/gentium-book-basic.woff2",
            routing::get(get_resource_gentiumbookbasic),
        );

    if allow_writes {
        ro_app
            .route("/new", routing::get(get_new))
            .route("/new", routing::post(post_new))
    } else {
        ro_app
    }
}

async fn fallback_404() -> Error {
    error_file_not_found()
}

///////////////////////////////////////////////////////////////////////////////

#[derive(Clone)]
struct AppState {
    es_host: String,
    allow_writes: bool,
}

impl AppState {
    fn elasticsearch(&self) -> Result<Elasticsearch, elasticsearch::Error> {
        Transport::single_node(&self.es_host).map(Elasticsearch::new)
    }

    fn context(&self) -> tera::Context {
        let mut context = tera::Context::new();
        context.insert("allow_writes", &self.allow_writes);
        context
    }
}

///////////////////////////////////////////////////////////////////////////////

async fn get_index() -> Redirect {
    Redirect::permanent("/search")
}

///////////////////////////////////////////////////////////////////////////////

async fn get_search(
    Query(query): Query<FormSearchQuery>,
    State(state): State<AppState>,
) -> Result<Html<String>, Error> {
    let q = if let Some(q) = &query.q {
        let trimmed = q.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed)
        }
    } else {
        None
    };

    let client = state
        .elasticsearch()
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let result = es::search(&client, q, query.page.unwrap_or(1))
        .await
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let mut context = state.context();
    context.insert("q", &q);
    context.insert("domains", &ranked_aggregate(result.domains));
    context.insert("tags", &ranked_aggregate(result.tags));
    context.insert(
        "results",
        &result
            .results
            .into_iter()
            .map(present_result)
            .collect::<Vec<_>>(),
    );
    context.insert("total", &result.total);
    context.insert("page", &result.page);
    context.insert("pages", &result.pages);

    render_html("search.html", &context)
}

#[derive(Deserialize)]
struct FormSearchQuery {
    q: Option<String>,
    page: Option<u64>,
}

fn present_result((record, fragment): (es::Record, Option<String>)) -> Value {
    let ellipsis_fragment = match fragment {
        Some(s) => {
            let plain: String = s.replace("<mark>", "").replace("</mark>", "");
            match (
                record.content.starts_with(&plain),
                record.content.ends_with(&plain),
            ) {
                (true, true) => s,
                (true, false) => s + "…",
                (false, true) => "…".to_string() + &s,
                (false, false) => "…".to_string() + &s + "…",
            }
        }
        None => String::new(),
    };

    let (url, parts) = if record.title.len() == 1 {
        (Some(record.url[0].clone()), None)
    } else {
        let parts = std::iter::zip(&record.title[1..], record.url)
            .map(|(title, url)| json!({"title": title, "url": url}))
            .collect::<Vec<_>>();
        (None, Some(parts))
    };

    json!({
        "title": record.title[0],
        "url": url,
        "domain": record.domain,
        "tag": record.tag,
        "parts": parts,
        "fragment": ellipsis_fragment,
    })
}

fn ranked_aggregate(mut agg: HashMap<String, u64>) -> Vec<(u64, String)> {
    let mut vec: Vec<_> = agg.drain().map(|(k, v)| (v, k)).collect();
    vec.sort();
    vec.reverse();
    vec
}

///////////////////////////////////////////////////////////////////////////////

async fn get_new(State(state): State<AppState>) -> Result<Html<String>, Error> {
    let client = state
        .elasticsearch()
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let tags = es::list_tags(&client)
        .await
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let mut context = state.context();
    context.insert("tags", &tags);

    render_html("new.html", &context)
}

async fn post_new(State(state): State<AppState>, form: Multipart) -> Result<Html<String>, Error> {
    let client = state
        .elasticsearch()
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let record = form_to_record(form).await?;

    es::delete(&client, &record)
        .await
        .map_err(|_| error_cannot_connect_to_search_server())?;
    es::put(&client, &record)
        .await
        .map_err(|_| error_cannot_connect_to_search_server())?;

    let mut context = state.context();
    context.insert("result", &present_result((record, None)));

    render_html("success.html", &context)
}

async fn form_to_record(mut form: Multipart) -> Result<es::Record, Error> {
    let mut collection_title = None;
    let mut tag = Vec::with_capacity(3);
    let mut url = Vec::with_capacity(1);
    let mut title = Vec::with_capacity(1);
    let mut content = None;

    while let Some(field) = form.next_field().await.map_err(|_| error_bad_request())? {
        let name = field.name().ok_or(error_bad_request())?.to_string();
        let value = field
            .text()
            .await
            .map_err(|_| error_bad_request())?
            .trim()
            .to_string();
        if value.is_empty() {
            continue;
        }
        match name.as_str() {
            "collection_title" => collection_title = Some(value),
            "tag" => tag.push(value),
            "url" => url.push(value),
            "title" => title.push(value),
            "content" => content = Some(value),
            _ => return Err(error_bad_request()),
        }
    }

    if url.is_empty() || title.is_empty() {
        return Err(error_bad_request());
    }

    let title_sort = if let Some(t) = collection_title {
        title.insert(0, t.clone());
        t
    } else {
        title[0].clone()
    };

    let content = if let Some(s) = content {
        s
    } else {
        fetch_combined_url_contents(&url).await
    };

    let domain = reqwest::Url::parse(&url[0])
        .unwrap()
        .host_str()
        .unwrap()
        .to_string();

    Ok(es::Record {
        title,
        title_sort,
        url,
        domain,
        tag,
        content,
    })
}

async fn fetch_combined_url_contents(urls: &[String]) -> String {
    let mut handles = Vec::with_capacity(urls.len());
    for url in urls {
        handles.push(tokio::spawn(fetch_url_content(url.clone())));
    }

    let mut results = Vec::with_capacity(handles.len());
    for handle in handles {
        if let Ok(result) = handle.await.unwrap() {
            results.push(result);
        }
    }

    results.join("\n")
}

async fn fetch_url_content(url: String) -> reqwest::Result<String> {
    let html = reqwest::get(url).await?.text().await?;
    let doc = scraper::Html::parse_document(&html);
    let text = doc.root_element().text();
    Ok(text.collect::<Vec<_>>().join(" "))
}

///////////////////////////////////////////////////////////////////////////////

lazy_static! {
    static ref TEMPLATES: Tera = {
        let mut tera = Tera::default();
        let res = tera.add_raw_templates(vec![
            (
                "_result.partial.html",
                include_str!("_templates/_result.partial.html.tera"),
            ),
            ("new.html", include_str!("_templates/new.html.tera")),
            ("search.html", include_str!("_templates/search.html.tera")),
            ("success.html", include_str!("_templates/success.html.tera")),
        ]);
        if let Err(error) = res {
            panic!("could not parse templates: {error}");
        }
        tera
    };
}

fn render_html(template: &str, context: &tera::Context) -> Result<Html<String>, Error> {
    match TEMPLATES.render(template, context) {
        Ok(rendered) => Ok(Html(rendered)),
        Err(_) => Err(error_something_went_wrong()),
    }
}

///////////////////////////////////////////////////////////////////////////////

const RESOURCE_STYLE_CSS: &[u8] = include_bytes!("_resources/style.css");
const RESOURCE_SEARCH_SVG: &[u8] = include_bytes!("_resources/search.svg");
const RESOURCE_FONT_FIRAMONO: &[u8] = include_bytes!("_resources/fira-mono.woff2");
const RESOURCE_FONT_GENTIUMBOOKBASIC: &[u8] = include_bytes!("_resources/gentium-book-basic.woff2");

async fn get_resource_stylesheet() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, mime::TEXT_CSS_UTF_8.essence_str())],
        RESOURCE_STYLE_CSS,
    )
}

async fn get_resource_searchsvg() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, mime::IMAGE_SVG.essence_str())],
        RESOURCE_SEARCH_SVG,
    )
}

async fn get_resource_firamono() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, mime::FONT_WOFF2.essence_str())],
        RESOURCE_FONT_FIRAMONO,
    )
}

async fn get_resource_gentiumbookbasic() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, mime::FONT_WOFF2.essence_str())],
        RESOURCE_FONT_GENTIUMBOOKBASIC,
    )
}

///////////////////////////////////////////////////////////////////////////////

const TEMPLATE_ERROR_HTML: &str = include_str!("_templates/error.html.tera");

#[derive(Debug)]
struct Error {
    status_code: StatusCode,
    message: String,
}

impl IntoResponse for Error {
    fn into_response(self) -> Response<Body> {
        let mut context = tera::Context::new();
        context.insert("status_code", &u16::from(self.status_code));
        context.insert("message", &self.message);

        if let Ok(rendered) = Tera::one_off(TEMPLATE_ERROR_HTML, &context, true) {
            (self.status_code, Html(rendered)).into_response()
        } else {
            (self.status_code, self.message.clone()).into_response()
        }
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", u16::from(self.status_code), self.message)
    }
}

fn error_cannot_connect_to_search_server() -> Error {
    Error {
        status_code: StatusCode::SERVICE_UNAVAILABLE,
        message: "The search server is unavailable.  Try again in a minute or two.".to_string(),
    }
}

fn error_bad_request() -> Error {
    Error {
        status_code: StatusCode::BAD_REQUEST,
        message: "Bad request.".to_string(),
    }
}

fn error_file_not_found() -> Error {
    Error {
        status_code: StatusCode::NOT_FOUND,
        message: "The requested file does not exist.".to_string(),
    }
}

fn error_something_went_wrong() -> Error {
    Error {
        status_code: StatusCode::INTERNAL_SERVER_ERROR,
        message: "Something went wrong.".to_string(),
    }
}
