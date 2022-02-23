FROM python:3-slim

ENV DISPLAY=:99
ENV DEBIAN_FRONTEND=noninteractive
ENV TOR_VERSION=0.4.6.10
ENV TOR_CMD=/usr/local/bin/tor

RUN apt-get update -qq
RUN apt-get install -yqq curl xvfb firefox-esr build-essential libevent-dev libssl-dev zlib1g-dev
RUN curl -fsSL https://github.com/mozilla/geckodriver/releases/download/v0.30.0/geckodriver-v0.30.0-linux64.tar.gz | tar zxf - -C /usr/local/bin

RUN curl -fsSL https://dist.torproject.org/tor-${TOR_VERSION}.tar.gz | tar xzf - \
  && cd tor-${TOR_VERSION} \
  && ./configure \
  && make -j$(nproc) \
  && make install \
  && cd .. \
  && rm -rf tor-${TOR_VERSION}

RUN mkdir /app
COPY app.py requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt

COPY docker-entrypoint.sh /
ENTRYPOINT ["/docker-entrypoint.sh"]
