FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends swaks libnet-ssleay-perl libio-socket-ssl-perl ca-certificates tzdata \
      libreoffice-writer-nogui fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation2 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir requests pypdf cryptography \
 && useradd --uid 1000 --create-home app \
 && mkdir /data && chown app /data

WORKDIR /app
COPY monitor.py extras.py server.py users.py prefs.py match.py docfiles.py appprofile.py tailor.py llm.py employers.py letters.py autofill.user.js site-templates.json mailer.py polite.py emailfmt.py unsub.py run.py index.html config.json phrases.json ./
COPY assets ./assets
USER app
EXPOSE 31361
CMD ["python3", "-u", "run.py"]
