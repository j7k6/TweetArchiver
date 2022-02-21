FROM python:3-slim

ENV DISPLAY=:99

RUN apt-get update
RUN apt-get install -y curl xvfb firefox-esr
RUN curl -fsSL https://github.com/mozilla/geckodriver/releases/download/v0.30.0/geckodriver-v0.30.0-linux64.tar.gz | tar zxf - -C /usr/local/bin

RUN mkdir /app
COPY app.py requirements.txt /app
WORKDIR /app
RUN pip install -r requirements.txt

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
