#! /bin/bash

source base.sh

pre-commit && python_run -m ruff check .
