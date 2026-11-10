import os

import psycopg

def connect():
    """Open a connect to Postgres using DATABASE_URL from docker-compose."""
    return psycopg.connect(os.environ["DATABASE_URL"])
