# pixeltable-marketplace

A secondhand marketplace app. Sellers post photos, and Gemini writes the listing. Shoppers search the listings or ask for what they want.

| To | Send | Get back |
|---|---|---|
| Post a listing: `POST /listings` | seller name, price, three photos | the listing Gemini wrote from the photos (title, category, condition, color, description), the first photo cropped to the item, and an 11-second video: the three photos with a slow zoom, the title and price as a caption, and Gemini's voice reading a two-sentence pitch |
| See a listing: `GET /listings/{id}` | listing ID | seller, price, title and Gemini's listing |
| Search in words: `GET /search` | a description, e.g. "warm light for a reading nook", and optionally a condition | the closest listings, by their first photo |
| Search with a photo: `POST /similar` | a photo | the closest listings, by their first photo |
| Ask: `python agent.py` | a question, e.g. "a like-new lamp under $100?" | the listings that fit, each with a reason, and a note to the shopper |

The app is built with FastAPI and Pydantic, with [Pixeltable](https://github.com/pixeltable/pixeltable) as its database.

You already know type safety from Pydantic. Pixeltable extends it to the images, video and LLM output you store, and guarantees that everything derived from them is made the same way for every file. This app shows it in three places:

- **Every row.** Your Pydantic model defines the shape of your data. Pixeltable calls your functions, including LLMs, on every row, and stores each result in that shape. Everything derived from your files is made the same way for every file, e.g., frames are extracted at the frame rate you set, and an index is always queried with the embedding model that built it. Here, Gemini writes every listing from the seller's photos, in the shape of the Pydantic model `ListingDetails`.
- **Coming in.** Pixeltable checks every image, video, audio file and document at insert, and can validate outputs, including from LLMs, against your Pydantic model. So a bad file or a bad LLM output can't break your app. Here, an upload that isn't an image is refused before Gemini sees it, and Gemini's JSON is validated against `ListingDetails`.
- **Going out.** Pixeltable returns data as your Pydantic models, in query results and in your API's responses, so your editor, your type checker and FastAPI can use it directly. Here, `GET /listings/{id}` returns a `Listing`, and the `/listings` route types `details` as `ListingDetails`.

Every listing's `details` has the same fields, so the app can query what Gemini wrote like any other data. `condition` is its own column, taken from what Gemini wrote, so `/search` filters on it the same way the app could filter on the price the seller set.

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

Here is the `Listings` table in `app.py`:

- The photo columns have Pixeltable's `Image` type, so Pixeltable opens each upload and refuses one that isn't an image.
- When a column is set to a Pixeltable call, like `pxtf.gemini.generate_content`, Pixeltable runs that call on every new row.
- `parse_details()` validates Gemini's JSON against `ListingDetails`, and its return type makes `ListingDetails` the type of the `details` column. An answer that doesn't fit fails the insert.
- The fields the app filters on or uses, like `condition`, are their own typed columns.

```python
@pxt.udf
def parse_details(raw: str) -> pxt.Json[ListingDetails]:
    return ListingDetails.model_validate_json(raw).model_dump()


class Listings(TableModel, name='listings'):
    id = pxt.Column(value=pxtf.uuid.uuid7(), primary_key=True)
    seller: pxt.String
    price: pxt.Float
    photo_1: pxt.Image
    photo_2: pxt.Image
    photo_3: pxt.Image

    # The listing's details, validated against ListingDetails; an answer that doesn't fit fails the insert.
    response = pxtf.gemini.generate_content(
        [DETAILS_PROMPT, photo_1, photo_2, photo_3], model=MODEL, config=json_config(ListingDetails)
    )
    details = parse_details(gemini_text(response))
    title = details.title.astype(pxt.String)
    condition = details.condition.astype(pxt.String)
    ...
```

The app also does these things, each from a column or query in the same file, with no worker or sync script:

- Each listing gets an 11-second video made from its photos and narrated by Gemini.
- `/search` finds listings by their first photo from a description in words, optionally only in one condition.
- `agent.py` answers shoppers' questions as a Pydantic AI agent. It searches and queries the listings table and returns `Picks`, the listings it chose for the shopper.

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

If you use a coding agent, run `pxt skills install`. It adds the Pixeltable skill, which covers the `pxt` commands, to this folder for your agent to read.

### 2. Create the tables and start the app

```bash
pxt schema update app.py market
pxt service update app.py market
pxt service list
```

Each `update` command shows its plan and asks before it applies it.

`pxt service list` prints the app's URL, e.g. `http://127.0.0.1:53924`. Use that URL as `<url>` below.

### 3. Post a listing

```bash
curl -X POST <url>/listings -F seller=you -F price=260 \
  -F photo_1=@samples/guitar-1.jpg -F photo_2=@samples/guitar-2.jpg -F photo_3=@samples/guitar-3.jpg
```

The POST starts a background job and returns the job's `id` and a `job_url` right away, because the Gemini calls and the video take about 15 seconds. The job's `id` isn't your listing's `id`. Put the `job_url` in the command below, and run the command until `status` is `done`:

```bash
curl <job_url>
```

The finished job's `result` is your listing:

- `id`: the listing's ID, for step 5
- `details`: what Gemini wrote from the photos, as the Pydantic model `ListingDetails`
- `promo`: the video. Open the link in a browser.

### 4. Post a file that isn't an image

```bash
echo "not an image" > not-a-photo.jpg
curl -X POST <url>/listings -F seller=you -F price=10 \
  -F photo_1=@not-a-photo.jpg -F photo_2=@samples/guitar-2.jpg -F photo_3=@samples/guitar-3.jpg
```

Run `curl` on the new `job_url`. The job fails with `INVALID_DATA_FORMAT` and `Not a valid image`. Pixeltable refuses the whole insert, so no listing is stored, and Gemini never sees the file.

### 5. See the stored row

Use the `id` from the finished job's `result` as `<listing_id>`:

```bash
pxt get market/listings <listing_id> --cols title,price,narration,promo
```

`app.py` sets the `/listings` route to return four columns. The row in Pixeltable has every column, including `narration`, the audio of Gemini reading the pitch. `narration` and `promo` are file paths you can open.

If a listing fails, see why:

```bash
pxt errors market/listings
```

### 6. Post the 19 sample listings

```bash
python scripts/seed.py <url>
```

### 7. Query what Gemini wrote

If Gemini wrote free text, one listing might say "like-new" and another "barely used", and a filter would miss one of them. Every stored `details` fits `ListingDetails`, where `condition` can only be `new`, `like new`, `good` or `fair`. Because Gemini can't write any other value, one filter finds every like-new listing.

Start a Python shell in this folder. `bind_all('market')` connects the table classes in `app.py` to the `market` tables you created in step 2:

```python
from app import Listings, TableModel

TableModel.bind_all('market')
Listings.where(Listings.condition == 'like new').select(Listings.title, Listings.price).collect()
```

The query returns the like-new listings, e.g. `Black Adjustable LED Desk Lamp` at 45.0. Gemini writes each condition, so the count can differ from run to run.

### 8. Search the photos in words

From the API:

```bash
curl "<url>/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl "<url>/search?q=lamp&condition=like%20new"
```

From the same Python shell:

```python
score = Listings.photo_1.similarity(string='warm light for a reading nook')
Listings.order_by(score, asc=False).limit(3).select(Listings.title, Listings.price, score=score).collect()
```

The `/search` route serves `search`, a query function in `app.py`. The Python code runs the same query directly.

### 9. Ask a question

The Pydantic AI agent searches and queries the listings table, and answers as `Picks`: the listings it chose, each with a `why`, and a `note` to the shopper. Its output validator checks that every pick is a real listing at its real price.

```bash
python agent.py "Something warm to read by, under \$150?"
```

### 10. See every step in Logfire

Create a project in [Logfire](https://logfire.pydantic.dev), and make a write token for it. Then set these in the shell where you run `pxt`:

```bash
export LOGFIRE_TOKEN=<your write token>
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=$LOGFIRE_TOKEN"
export OTEL_SERVICE_NAME=marketplace
export OTEL_SPAN_LEVEL=debug
```

If your Logfire project is in the EU, use `https://logfire-eu.pydantic.dev` instead.

The Pixeltable daemon reads the environment only when it starts, so restart it. Then restart the app with `--otel`:

```bash
pxt daemon restart
pxt service update app.py market --otel
```

Post a listing as in step 3. In Logfire, the listing is a `pixeltable.insert` trace, with a span for each call Pixeltable made to fill the row's columns. Each span names its column. In one run, Gemini took 12.7 seconds to write `response`, 4.3 seconds to read the pitch into `narration`, and 1.6 seconds to embed the first photo for search. The `POST /listings` request is a separate trace, because the route returns a job before the insert runs.

`agent.py` sends its own traces to Logfire when `LOGFIRE_TOKEN` is set. Each Pixeltable query the agent runs shows up under the tool call that ran it.

To let a coding agent such as Claude Code read these traces, add the [Logfire MCP server](https://pydantic.dev/docs/logfire/guides/mcp-server/):

```bash
claude mcp add --transport http logfire https://logfire-us.pydantic.dev/mcp
claude mcp login logfire
```

## Files

- `app.py`: the app: the Pydantic models, the `Listings` table, and the FastAPI routes, which Pixeltable's `FastAPIRouter` builds from the tables and queries. `pxt schema update` creates the tables from this file, and `pxt service update` serves the routes.
- `agent.py`: the buyer's agent, built with Pydantic AI. The agent searches and queries the listings table with tools from Pixeltable's add-on for Pydantic AI Harness, a package of add-ons for Pydantic AI agents. `pyproject.toml` installs it as `pydantic-ai-harness[pixeltable]` (0.66.0 or later, released in Pydantic AI 2.66.0).
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: runs 17 searches, each with a known right listing. `/search` ranks that listing first in all 17.
