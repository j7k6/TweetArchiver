FROM python:3-slim

ENV DISPLAY=:99
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq
RUN apt-get install -yqq curl xvfb firefox-esr
RUN curl -fsSL https://github.com/mozilla/geckodriver/releases/download/v0.30.0/geckodriver-v0.30.0-linux64.tar.gz | tar zxf - -C /usr/local/bin

RUN mkdir /app
COPY app.py requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
