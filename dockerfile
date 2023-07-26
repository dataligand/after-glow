# syntax=docker/dockerfile:1
FROM python:3.11-alpine as build

WORKDIR '/build'

RUN apk add --no-cache poetry python3-dev libffi-dev

COPY pyproject.toml poetry.lock .

RUN poetry export > requirements.txt && mkdir packages && pip install -r requirements.txt -t packages

FROM alpine:latest

RUN apk add --no-cache python3 openssh

RUN addgroup -g 1000 app && adduser -D -u 1000 -G app app

WORKDIR '/home/app'

COPY --from=build --chown=app:app /build/packages ./packages
COPY --chown=app:app afterglow afterglow/

ENV PYTHONPATH=/home/app/packages

EXPOSE 8022

USER app:app

ENTRYPOINT ["python3", "-m", "afterglow"]
