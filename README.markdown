bookmarks
=========

A database and web app to keep track of my bookmarks, deployed to [bookmarks.barrucadu.co.uk](http://bookmarks.barrucadu.co.uk/).

![screenshot](screenshot.png)

## Running

There's a docker-compose file provided, which will fire up a read-write instance
of bookmarks accessible at `http://localhost:8888`:

```bash
docker-compose up
```

You will then need to create the search index:

```bash
docker-compose exec bookmarks /app/create-index.py
```

I run bookmarks [via nix](https://github.com/barrucadu/nixfiles/blob/master/shared/bookmarks/default.nix).
