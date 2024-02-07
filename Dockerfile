FROM python:3.13.0a3 AS base
RUN useradd -m app
WORKDIR /app

FROM base AS poetry
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV PATH="$POETRY_HOME/bin:$PATH"
ENV POETRY_NO_INTERACTION=1
RUN curl -sSL https://install.python-poetry.org | python -
COPY poetry.lock pyproject.toml ./
RUN poetry install

FROM base AS app
ENV PATH="/app/.venv/bin:$PATH"
ENV ELASTIC_CLIENT_APIVERSIONING=1
COPY --chown=app bookmarks /app/bookmarks
COPY --from=poetry /app/.venv /app/.venv
USER app

CMD ["gunicorn", "-w", "4", "-t", "60", "-b", "0.0.0.0:8888", "bookmarks.serve:app"]
