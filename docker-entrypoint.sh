#!/bin/bash
set -e

Xvfb :99 -screen 0 1024x2048x16 -nolisten tcp &

exec python app.py "$@"
