import os

import httpx
from psycopg.types.json import Jsonb

from cfb.db import connect

BASE_URL = "https://api.collegefootballdata.com"


def get(endpoint, params, refresh=False):
    """Return CFBD data for endpoint + params.

    Uses the saved copy in api_responses if we have one.  Only calls the API
    (spending 1 of our monthly calls) when it's missing or refresh=True.
    """
    with connect() as conn:
        if not refresh:
            row = conn.execute(
                """
                SELECT body FROM api_responses
                WHERE source = 'cfbd' AND endpoint = %s AND params = %s
                """,
                (endpoint, Jsonb(params)),
            ).fetchone()
            if row is not None:
                return row[0]
        headers = {"Authorization": f"Bearer {os.environ['CFBD_API']}"}
        resp = httpx.get(BASE_URL + endpoint, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
        body = resp.json()

        conn.execute(
            """
            INSERT INTO api_responses (source, endpoint, params, status, body)
            VALUES ('cfbd', %s, %s, %s, %s)
            ON CONFLICT (source, endpoint, params)
            DO UPDATE SET status = EXCLUDED.status,
                          body = EXCLUDED.body,
                          fetched_at = now()
            """,
            (endpoint, Jsonb(params), resp.status_code, Jsonb(body)),
        )
        print(f"CFBD call used: {endpoint} {params} ({resp.headers.get('x-calllimit-remaining', '?')} left)")
        return body
