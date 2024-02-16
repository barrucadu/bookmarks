use std::io;
use std::net::SocketAddr;

pub async fn serve(es_host: String, address: SocketAddr, allow_writes: bool) -> io::Result<()> {
    println!("serve: {es_host} / {address} / {allow_writes}");
    Ok(())
}
