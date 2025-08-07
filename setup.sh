#!/usr/bin/env bash
set -e

pip install -r requirements.txt
playwright install

echo "Reminder: Copy .env.example to .env and populate credentials."
