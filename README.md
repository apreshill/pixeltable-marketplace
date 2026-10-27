# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, with [Pixeltable](https://github.com/pixeltable/pixeltable) as its database.

If you use Pydantic, you define a model once and use that model everywhere. Pixeltable can use a Pydantic model as a column type. In this app, one Pydantic model, `ListingDetails`, is:

- the JSON Gemini must return for each listing
- the type of the `details` column
- part of the `Listing` that `GET /listings/{id}` returns

```
Without Pixeltable                         With Pixeltable

FastAPI + Pydantic                         FastAPI + Pydantic
   │                                          │
   ├─ Postgres: rows and file paths           └─ Pixeltable, as tables in app.py:
   ├─ S3: the photos                               rows, photos, image checks on uploads,
   ├─ code that checks each file is an image       Gemini calls, video, search index
   ├─ workers that call Gemini
   │    and make the listing video
   └─ a vector database, plus a script that
        copies new rows into the vector database
```

When a seller posts three photos and a price, Pixeltable:

- stops any upload that isn't an image before Gemini or the video step sees the upload
- has Gemini write the listing from the photos
- makes an 11-second video from the photos, narrated by Gemini
- indexes the first photo for `/search`, so shoppers can find the listing by describing the item in words

Shoppers can also ask a question, like "something warm to read by, under $150", and get matching listings back from `POST /ask`. `agent.py` answers the same questions as `POST /ask`, with Pydantic AI.

## Run the app

You need Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg`, and `GEMINI_API_KEY` set in your environment. The `-f` flag skips the confirmation prompts.

```bash
uv sync
source .venv/bin/activate
pxt schema update app.py market -f   # create the tables in a local database named market
pxt service update app.py market -f  # start the app on localhost
pxt service list                     # print the app's URL
URL=http://127.0.0.1:PORT            # the URL that pxt service list printed

python scripts/seed.py $URL          # post 19 sample listings
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by, under $150?"}'
python agent.py "Something warm to read by, under \$150?"
```

## Files

- `app.py`: the whole app, including the Pydantic models, the tables, and the routes
- `agent.py`: a Pydantic AI agent that reads the listings table through Pixeltable's add-on for Pydantic AI Harness. The add-on isn't released yet, so `pyproject.toml` installs the add-on from the branch of [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: 17 searches with a known right answer. `/search` puts the right listing first in all 17
