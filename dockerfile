# syntax=docker/dockerfile:1
FROM python:3.11-alpine as build

WORKDIR '/build'

RUN apk add poetry python3-dev libffi-dev

COPY pyproject.toml poetry.lock .

RUN poetry export > requirements.txt && mkdir packages && pip install -r requirements.txt -t packages

FROM alpine:latest

RUN apk add python3 openssh

WORKDIR '/app'

COPY --from=build /build/packages ./packages
COPY afterglow afterglow/

ENV PYTHONPATH=/app/packages

EXPOSE 8022

ENTRYPOINT ["python3", "-m", "afterglow"]