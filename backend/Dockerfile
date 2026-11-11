FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gdal-bin libgdal-dev libgeos-dev libproj-dev libpq-dev gettext \
    && apt-get clean \
    && find /var/lib/apt/lists -type f -delete

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY --chown=app:app . .

USER app

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
