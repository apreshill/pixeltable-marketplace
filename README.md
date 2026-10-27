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

Here is the first of those steps in `app.py`, on a Pixeltable table class. A column with a type stores what the seller sends. A column set to a Pixeltable call, like `pxtf.gemini.generate_content`, runs that call on every new row:

```python
class Listings(TableModel, name='listings'):
    id = pxt.Column(value=pxtf.uuid.uuid7(), primary_key=True)
    seller: pxt.String
    price: pxt.Float
    photo_1: pxt.Image
    photo_2: pxt.Image
    photo_3: pxt.Image

    # Gemini writes the listing from the photos; parse_details() turns Gemini's JSON into a ListingDetails.
    response = pxtf.gemini.generate_content(
        [PROMPT, photo_1, photo_2, photo_3], model='gemini-3.8-flash', config=LISTING_CONFIG
    )
    details = parse_details(response.candidates[0].content.parts[0].text.astype(pxt.String))
    ...
```

Shoppers can also ask a question, like "something warm to read by, under $150", and get matching listings back from `POST /ask`. Gemini calls the app's `find_listings` query as a tool, Pixeltable runs the query, and Gemini picks from the results. If your agents already run on Pydantic AI, `agent.py` does the same job as a Pydantic AI agent that reads the same listings table and returns the same `Picks` model.

## Explore it with your coding agent

To have a coding agent such as Claude Code, Cursor, or Codex run the app for you, first install the Pixeltable skill in this folder, so the agent knows the `pxt` commands:

```bash
uv sync
source .venv/bin/activate
pxt skills install
```

Then paste this prompt into your agent:

```text
Run this app locally by following the "Run the app" steps in README.md. GEMINI_API_KEY is already set. Post one listing from samples/, poll its job_url until status is done, then show me the stored row with pxt get market/listings <id> --cols title,price,narration,promo, using the id from the job's result. Then walk me through the Listings class in app.py: for each column, say what the column stores or computes, and which other columns that column reads. Use the pxt CLI to look at the tables. Don't change app.py.
```

## Run the app

You need:

- Python 3.12 to 3.14
- [uv](https://docs.astral.sh/uv/)
- `ffmpeg`
- `GEMINI_API_KEY` set in your environment

### 1. Install

```bash
uv sync
source .venv/bin/activate
```

### 2. Create the tables and start the app

```bash
pxt schema update app.py market -f
pxt service update app.py market -f
pxt service list
```

`pxt service list` prints the app's URL, e.g. `http://127.0.0.1:53924`. Use that URL as `<url>` below.

### 3. Post a listing

```bash
curl -X POST <url>/listings -F seller=you -F price=260 \
  -F photo_1=@samples/guitar-1.jpg -F photo_2=@samples/guitar-2.jpg -F photo_3=@samples/guitar-3.jpg
```

The app returns a `job_url` right away, because Gemini and the video take about 15 seconds. Check the job until `status` is `done`:

```bash
curl <job_url>
```

The finished job's `result` is your listing:

- `details`: what Gemini wrote from the photos, as the Pydantic model `ListingDetails`
- `promo`: the video. Open the link in a browser.
- `id`: the listing's ID, for step 4

### 4. See the stored row

```bash
pxt get market/listings <id> --cols title,price,narration,promo
```

`app.py` sets the `/listings` route to return four columns. The row in Pixeltable has every column, including `narration`, the audio of Gemini reading the pitch. `narration` and `promo` are file paths you can open.

If a listing fails, see why:

```bash
pxt errors market/listings
```

### 5. Post the 19 sample listings

```bash
python scripts/seed.py <url>
```

### 6. Search the photos in words

From the API:

```bash
curl "<url>/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
```

From Python, with the Pixeltable SDK, in a Python shell:

```python
from app import Listings, TableModel

TableModel.bind_all('market')
score = Listings.photo_1.similarity(string='warm light for a reading nook')
Listings.order_by(score, asc=False).limit(3).select(Listings.title, Listings.price, score=score).collect()
```

The `/search` route serves `search`, a query function in `app.py`. The Python code runs the same query directly.

### 7. Ask a question

```bash
curl -X POST <url>/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by, under $150?"}'
```

The `/ask` request returns a `job_url` too. The answer is in the finished job's `result`.

Ask the same question through the Pydantic AI agent:

```bash
python agent.py "Something warm to read by, under \$150?"
```

## Files

- `app.py`: the app: the Pydantic models, the Pixeltable tables (`Listings` for listings, `Asks` for shoppers' questions), and the FastAPI routes, which Pixeltable's `FastAPIRouter` builds from the tables and queries. `pxt schema update` creates the tables from this file, and `pxt service update` serves the routes.
- `agent.py`: the Pydantic AI version of `POST /ask`. The agent searches and queries the listings table with tools from Pixeltable's add-on for Pydantic AI Harness, a package of add-ons for Pydantic AI agents. The add-on isn't released yet, so `pyproject.toml` installs the add-on from the branch of [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: runs 17 searches, each with a known right listing. `/search` ranks that listing first in all 17.
