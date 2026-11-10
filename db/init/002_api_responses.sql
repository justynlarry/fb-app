-- Raw API responses, saved before parsing, so the same call isn't paid for twice

CREATE TABLE api_responses (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      TEXT NOT NULL,          -- 'cfbd' (later maybe 'nflverse')
    endpoint    TEXT NOT NULL,          -- '/games'
    params      JSONB NOT NULL,         -- {"year": 2024, "seasonType": "regular"}
    status      SMALLINT NOT NULL,      -- HTTP status code, 200 = OK
    body        JSONB NOT NULL,         -- the response exactly as received
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, endpoint, params)
);

