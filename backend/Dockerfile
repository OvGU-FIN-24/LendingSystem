FROM python:3.12.15-slim

WORKDIR /backend

# Unbuffered output so print() logs reach `docker compose logs` immediately
ENV PYTHONUNBUFFERED=1

# System dependencies for mysqlclient; build tools are removed again in the same layer.
# gunicorn 20.1.0 imports pkg_resources, which setuptools >= 81 no longer ships (follow-up: gunicorn >= 23).
COPY requirements.txt /backend/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends pkg-config default-libmysqlclient-dev build-essential \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir setuptools==80.9.0 \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /backend/
# Default templates (build context "templates", see docker-compose.yml); seed the template-files volume
COPY --from=templates . /backend/templates/
# Placeholder picture referenced by the frontend; seeds the image-files volume
COPY static-seed/platzhalter_bild.png /backend/pictures/1741980710.2106326_platzhalter_bild.png

RUN useradd -u 10001 -U -M -d /backend app \
    && mkdir -p pictures pdfs templates \
    && chown -R 10001:10001 pictures pdfs templates

USER 10001
EXPOSE 5000

CMD [ "gunicorn", "-w", "1", "--timeout", "120", "--access-logfile", "-", "-b", "0.0.0.0:5000", "app:app" ]
