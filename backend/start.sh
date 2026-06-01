#!/bin/bash
python bootstrap_db.py
exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 2
