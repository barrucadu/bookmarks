FROM python:3.8

COPY requirements-freeze.txt .
RUN pip install -r requirements-freeze.txt

RUN useradd -m app
COPY --chown=app src /app
COPY --chown=app config /app/config
WORKDIR /app
USER app

CMD /app/serve.py
