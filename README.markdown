bookmarks
=========

A database and web app to keep track of my bookmarks, deployed to [bookmarks.nyarlathotep](http://bookmarks.nyarlathotep/).

![screenshot](screenshot.png)

## Build / deploy a new release

```
docker build -t localhost:5000/bookmarks:latest .
docker push localhost:5000/bookmarks:latest
sudo systemctl restart bookmarks
```
