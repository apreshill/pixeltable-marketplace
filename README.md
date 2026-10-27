# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, with [Pixeltable](https://github.com/pixeltable/pixeltable) as its database.

If you use Pydantic, you define a model once and use it everywhere. Here the database uses it too. `ListingDetails` is the JSON Gemini must return when it writes a listing, the type of the column that stores it, and part of what `GET /listings/{id}` returns. Its fields are also queryable like any column: `Listings.where(Listings.details.category == 'home')`.

```
Without Pixeltable                         With Pixeltable

FastAPI + Pydantic                         FastAPI + Pydantic
   │                                          │
   ├─ Postgres: rows and file paths           └─ Pixeltable: the tables in app.py
   ├─ S3: the photos
   ├─ code that checks each file is an image
   ├─ a worker queue: calls Gemini,
   │    makes the listing video
   └─ a vector database, plus the script
        that keeps it in sync
```

When a seller posts three photos and a price, Pixeltable:

- refuses a file that isn't an image, with a 422
- has Gemini write the listing from the photos
- makes a 10-second video from the photos, narrated by Gemini
- adds the first photo to search, so shoppers can find the listing by describing what they want

Shoppers can also ask a question, like "something warm to read by, under $150", and get matching listings back from `POST /ask`. `agent.py` answers the same questions with Pydantic AI.

## Run it

You need Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg`, and `GEMINI_API_KEY`.

```bash
uv sync
uv run pxt schema update app.py market -f   # create the tables
uv run pxt service update app.py market -f  # start the app on localhost
uv run pxt service list                     # print its URL
URL=http://127.0.0.1:PORT                   # the URL it printed

uv run python scripts/seed.py $URL          # post 19 sample listings
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by, under $150?"}'
uv run python agent.py "Something warm to read by, under \$150?"
```

## Files

- `app.py`: the whole app, including the Pydantic models, the tables, and the routes
- `agent.py`: the Pydantic AI agent. Its Pixeltable tools come from an add-on for Pydantic AI Harness that isn't released yet; `pyproject.toml` installs it from the branch of [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369)
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: 17 searches with a known right answer; `/search` puts the right listing first in all 17
