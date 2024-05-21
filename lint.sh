#!/bin/bash

set -e
set -x

# Requires flake8 for linting and mypy for type checks.
# "apt install flake8 mypy" or "pip install flake8 mypy"

# Start with just syntax errors and undefined names
flake8 . --count \
  --select=E9,F63,F7,F82 \
  --show-source \
  --statistics

# Now everything else, except for certain errors I've disabled
flake8 . --count \
  --indent-size=2 \
  --max-complexity=10 \
  --max-line-length=80 \
  --ignore=E126,E128,E221,E222,E262,W504 \
  --show-source \
  --statistics

# Now check types with mypy
mypy --strict flashkit/*.py
