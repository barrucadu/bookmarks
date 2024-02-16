use actix_web::http::StatusCode;
use actix_web::{get, post, web, App, HttpResponse, HttpServer, Responder, ResponseError};
use elasticsearch::http::transport::Transport;
use elasticsearch::Elasticsearch;
use std::net::SocketAddr;
use std::{fmt, io};

pub async fn serve(es_host: String, address: SocketAddr, allow_writes: bool) -> io::Result<()> {
    let app_state = web::Data::new(AppState {
        es_host,
        allow_writes,
    });

    HttpServer::new(move || {
        let ro_app = App::new()
            .app_data(app_state.clone())
            .default_service(web::to(fallback_404))
            .service(get_resource_stylesheet)
            .service(get_resource_searchsvg)
            .service(get_resource_firamono)
            .service(get_resource_gentiumbookbasic)
            .service(get_index)
            .service(get_search);
        if allow_writes {
            ro_app.service(get_new).service(post_new)
        } else {
            ro_app
        }
    })
    .bind(address)?
    .run()
    .await
}

async fn fallback_404() -> HttpResponse {
    error_file_not_found().error_response()
}

///////////////////////////////////////////////////////////////////////////////

struct AppState {
    es_host: String,
    allow_writes: bool,
}

impl AppState {
    fn elasticsearch(&self) -> Result<Elasticsearch, elasticsearch::Error> {
        Transport::single_node(&self.es_host).map(Elasticsearch::new)
    }
}

///////////////////////////////////////////////////////////////////////////////

#[get("/")]
async fn get_index() -> impl Responder {
    web::Redirect::to("/search").permanent()
}

#[get("/search")]
async fn get_search(state: web::Data<AppState>) -> Result<HttpResponse, Error> {
    match state.elasticsearch() {
        Ok(_client) => Err(error_something_went_wrong()),
        Err(_err) => Err(error_cannot_connect_to_search_server()),
    }
}

#[get("/new")]
async fn get_new(state: web::Data<AppState>) -> Result<HttpResponse, Error> {
    match state.elasticsearch() {
        Ok(_client) => Err(error_something_went_wrong()),
        Err(_err) => Err(error_cannot_connect_to_search_server()),
    }
}

#[post("/new")]
async fn post_new(state: web::Data<AppState>) -> Result<HttpResponse, Error> {
    match state.elasticsearch() {
        Ok(_client) => Err(error_something_went_wrong()),
        Err(_err) => Err(error_cannot_connect_to_search_server()),
    }
}

///////////////////////////////////////////////////////////////////////////////

const RESOURCE_STYLE_CSS: &[u8] = include_bytes!("_resources/style.css");
const RESOURCE_SEARCH_SVG: &[u8] = include_bytes!("_resources/search.svg");
const RESOURCE_FONT_FIRAMONO: &[u8] = include_bytes!("_resources/fira-mono.woff2");
const RESOURCE_FONT_GENTIUMBOOKBASIC: &[u8] = include_bytes!("_resources/gentium-book-basic.woff2");

#[get("/resources/style.css")]
async fn get_resource_stylesheet() -> HttpResponse {
    HttpResponse::Ok()
        .content_type(mime::TEXT_CSS_UTF_8)
        .body(RESOURCE_STYLE_CSS)
}

#[get("/resources/search.svg")]
async fn get_resource_searchsvg() -> HttpResponse {
    HttpResponse::Ok()
        .content_type(mime::IMAGE_SVG)
        .body(RESOURCE_SEARCH_SVG)
}

#[get("/resources/fira-mono.woff2")]
async fn get_resource_firamono() -> HttpResponse {
    HttpResponse::Ok()
        .content_type(mime::FONT_WOFF2)
        .body(RESOURCE_FONT_FIRAMONO)
}

#[get("/resources/gentium-book-basic.woff2")]
async fn get_resource_gentiumbookbasic() -> HttpResponse {
    HttpResponse::Ok()
        .content_type(mime::FONT_WOFF2)
        .body(RESOURCE_FONT_GENTIUMBOOKBASIC)
}

///////////////////////////////////////////////////////////////////////////////

const TEMPLATE_ERROR_HTML: &str = include_str!("_templates/error.html.tera");

#[derive(Debug)]
struct Error {
    status_code: StatusCode,
    message: String,
}

impl Error {
    fn html_error_response(&self) -> Result<HttpResponse, tera::Error> {
        let mut context = tera::Context::new();
        context.insert("status_code", &u16::from(self.status_code));
        context.insert("message", &self.message);

        let rendered = tera::Tera::one_off(TEMPLATE_ERROR_HTML, &context, true)?;
        Ok(HttpResponse::build(self.status_code)
            .content_type(mime::TEXT_HTML_UTF_8)
            .body(rendered))
    }

    fn fallback_error_response(&self) -> HttpResponse {
        HttpResponse::build(self.status_code)
            .content_type(mime::TEXT_PLAIN_UTF_8)
            .body(self.message.clone())
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", u16::from(self.status_code), self.message)
    }
}

impl ResponseError for Error {
    fn status_code(&self) -> StatusCode {
        self.status_code
    }

    fn error_response(&self) -> HttpResponse {
        self.html_error_response()
            .unwrap_or(self.fallback_error_response())
    }
}

fn error_cannot_connect_to_search_server() -> Error {
    Error {
        status_code: StatusCode::SERVICE_UNAVAILABLE,
        message: "The search server is unavailable.  Try again in a minute or two.".to_string(),
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
