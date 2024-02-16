bookmarks
=========

A database and web app to keep track of my bookmarks, deployed to
[bookmarks.barrucadu.co.uk](https://bookmarks.barrucadu.co.uk/).


Development
-----------

Install `rustup` and `openssl`, and then install the default toolchain:

```bash
rustup show
```

Then, compile in release mode:

```bash
cargo build --release
```

Run the unit tests with:

```bash
cargo test
```

### With nix

Open a development shell:

```bash
nix develop
```

And run cargo commands in there.


Usage
-----

Start up an Elasticsearch server and store the URL in the `ES_HOST` environment
variable.

Initialise the Elasticsearch index and start the server in read-write mode:

```bash
export ES_HOST="..."
./target/release/bookmarks_ctl create-index
./target/release/bookmarks --allow-writes
```

Omit the `--allow-writes` to launch in read-only mode.

Dump the Elasticsearch index as json to stdout with:

```bash
./target/release/bookmarks_ctl export-index > bookmarks.json
```

Restore it, overwriting the existing index:

```bash
./targets/release/bookmarks_ctl import-index --drop-existing < bookmarks.json
```

See the `--help` text for more.
