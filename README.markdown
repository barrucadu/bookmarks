bookmarks
=========

A database and web app to keep track of my bookmarks, deployed to [bookmarks.barrucadu.co.uk](http://bookmarks.barrucadu.co.uk/).

![screenshot](screenshot.png)

## Build / deploy a new release on nyarlathotep

```
docker build -t localhost:5000/bookmarks:latest .
docker push localhost:5000/bookmarks:latest
sudo systemctl restart bookmarks
```

## Build / deploy a new release on dunwich

This is automatically triggered by a push to the GitHub repository.
