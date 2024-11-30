FROM python:3-slim AS base
ENV PYBASE=/pybase
ENV PYTHONUSERBASE=$PYBASE
ENV PATH=$PYBASE/bin:$PATH

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    pip install pipenv
WORKDIR /tmp
COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv lock && \
    PIP_USER=1 PIP_IGNORE_INSTALLED=1 pipenv install --system --ignore-pipfile && \
    rm -rf /root/.cache

FROM base
WORKDIR /app
RUN mkdir -p /app/templates /app/static
COPY --from=builder /pybase /pybase
COPY __init__.py /app
COPY models.py /app
COPY config.py /app
COPY templates /app/templates
COPY static /app/static
EXPOSE 80
CMD [ "flask", "run", "--port=80", "--host=0.0.0.0" ]
