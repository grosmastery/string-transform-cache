# Cache service

A FastAPI microservice that builds "payloads" from two lists of strings and
caches the results of an expensive transformer function in a database, plus a
`cache-cli` command line client for exercising it.

## What it does

`POST /payload` takes two lists of equal length, transforms every string with
the transformer (a stand-in for an external service; here it upper-cases), and
interleaves the results:

```json
{"list_1": ["first string", "second string", "third string"],
 "list_2": ["other string", "another string", "last string"]}
```

```json
{"id": "7e29aab9-b651-499a-9317-857e5cf128e8", "message": "Payload created"}
```

`GET /payload/{id}` returns the stored result:

```json
{"output": "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"}
```

Interactive API docs are served at `/docs`.

## Caching design

The goal is to call the transformer as rarely as possible. Two layers do this:

1. **Payload deduplication.** Every request is fingerprinted with a SHA-256
   of its canonical JSON (`payload.input_hash`, unique). A request seen before
   returns the existing id with `200 OK` (new payloads get `201 Created`) and
   costs no transformer calls at all.
2. **String cache.** The `transformed_string` table maps each input string to
   its transformed value. For a new payload the service collects the distinct
   strings of both lists, loads the known ones in a single query, and calls
   the transformer only for the rest. A string repeated inside one request, or
   shared with any earlier request, is transformed exactly once, ever.

Reads (`GET`) only touch the `payload` table: the output is stored when the
payload is created, so reading never calls the transformer.

Concurrency: two requests may race to cache the same string or create the
same payload. String inserts use `INSERT ... ON CONFLICT DO NOTHING`
(identical values, so either winner is fine), and a payload insert that hits
the unique constraint falls back to the row the other request committed.

## Project layout

```
src/cache_service/   FastAPI service
  api.py             HTTP endpoints and dependencies
  service.py         payload generation and the transformer cache
  models.py          SQLModel tables
  schemas.py         request/response bodies
  transformer.py     the simulated external transformer
  db.py, config.py   engine/session handling and settings
  main.py            app factory and ASGI entry point
src/cache_cli/       cache-cli client (Pydantic Settings for argument parsing)
tests/               unit/, integration/ and cli/ tests
```

## Running

### Docker (PostgreSQL)

```bash
docker compose up --build
```

The API listens on <http://localhost:8000>. Compose sets a 0.2 s artificial
transformer delay so cache hits are visibly faster than misses.

The image alone also works, using SQLite inside the container:

```bash
docker build -t cache-service . && docker run -p 8000:8000 cache-service
```

### Locally (SQLite)

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn cache_service.main:app --reload
```

Configuration (environment variables or `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `CACHE_DATABASE_URL` | `sqlite:///./cache.db` | SQLAlchemy URL; SQLite or PostgreSQL (`postgresql+psycopg://...`) |
| `CACHE_TRANSFORMER_DELAY_SECONDS` | `0` | Simulated latency of the transformer |

## CLI

```
cache-cli [-h|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [--help]
```

| Option | Default | Meaning |
|---|---|---|
| `-h`, `--host` | `http://localhost:8000` | service base URL |
| `-r`, `--repeat` | `1` | number of create + read iterations (> 0) |
| `-i`, `--input` | | JSON input file, `-` for stdin |
| `-j`, `--json` | | input as a JSON string |
| `-o`, `--output` | `-` | output file, `-` for stdout |

Exactly one of `--input` / `--json` is required. Input is validated locally
(valid JSON, both lists present, non-empty and of equal length) before
anything is sent.

Each iteration posts the payload, reads it back and writes one JSON line:

```bash
uv run cache-cli -r 3 -i examples/payload.json
```

```
{"iteration": 1, "id": "7e29…", "created": true,  "elapsed_ms": 1205.3, "output": "FIRST STRING, …"}
{"iteration": 2, "id": "7e29…", "created": false, "elapsed_ms": 3.7,    "output": "FIRST STRING, …"}
{"iteration": 3, "id": "7e29…", "created": false, "elapsed_ms": 3.2,    "output": "FIRST STRING, …"}
```

```bash
cat examples/payload.json | uv run cache-cli -i - -o results.jsonl
uv run cache-cli -j '{"list_1": ["a", "b"], "list_2": ["c", "d"]}'
```

Exit codes: `0` success, `1` service error or unreachable, `2` invalid
arguments or unreadable input/output.

## Tests

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

- `tests/unit` covers interleaving, hashing and the cache logic against a real
  SQLite database (the logic is mostly SQL, so mocking the session would test
  little), counting transformer calls with a fake.
- `tests/integration` drives the HTTP API end to end with FastAPI's
  `TestClient`, including a restart to show the cache is persistent.
- `tests/cli` covers argument parsing/validation and runs the real CLI client
  against the app in-process.

## Decisions and shortcuts

- **`-h` means `--host`.** The brief lists `-h` for both `--host` and
  `--help`, which cannot both work. `-h` goes to `--host` (listed first and
  used far more often); help is available as `--help`.
- **Output format.** Strings are joined with `", "` as in the sample. A string
  that itself contains `", "` makes the output ambiguous to split; that is
  inherent to the requested format.
- **Order-sensitive identity.** Different order means different output, so
  `["a","b"]/["c","d"]` and `["b","a"]/["d","c"]` are different payloads
  (but share all cached strings).
- **Schema management** uses `SQLModel.metadata.create_all` at startup. A
  production service would use Alembic migrations.
- **Synchronous stack.** Endpoints are plain `def` and run in FastAPI's thread
  pool; the transformer is a sync call. An async driver would matter only
  with a real network-bound transformer under high load.
- **Cache never expires.** The transformer is deterministic, so entries stay
  valid forever; eviction would be needed only if storage became a concern.
- **Tests run on SQLite.** The PostgreSQL path (dialect-specific upsert) is
  exercised by running the service with Docker Compose, not by the test suite.
