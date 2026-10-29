# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, with [Pixeltable](https://github.com/pixeltable/pixeltable) as its database.

You already know type safety from Pydantic. Pixeltable extends it to the images, video and LLM output you store, and guarantees that every row is computed the same way. This app shows it in three places:

- **Every row.** Your Pydantic model defines the shape of your data. Pixeltable calls your functions, including LLMs, on every row, the same way, and stores each result in that shape. Here, Gemini writes every listing from the seller's photos, in the shape of the Pydantic model `ListingDetails`.
- **Coming in.** Pixeltable checks every image, video, audio file and document at insert, and can validate outputs, including from LLMs, against your Pydantic model. So a bad file or a bad LLM output can't break your app. Here, an upload that isn't an image is refused before Gemini sees it, and Gemini's JSON is validated against `ListingDetails`.
- **Going out.** Pixeltable returns data as your Pydantic models, in query results and in your API's responses, so your editor, your type checker and FastAPI can use it directly. Here, `GET /listings/{id}` returns a `Listing`, and the `/listings` route types `details` as `ListingDetails`.

Every listing's `details` has the same fields, so the app can query what Gemini wrote like any other data. A shopper can send "a like-new lamp under $100" to `POST /ask`, and the app filters on the condition Gemini wrote, the same way it filters on the price the seller set.

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
- `parse_details()` validates Gemini's JSON against `ListingDetails`, and its return type makes `ListingDetails` the type of the `details` column.

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

    # Gemini writes the listing from the photos; parse_details() turns Gemini's JSON into a ListingDetails.
    response = pxtf.gemini.generate_content(
        [PROMPT, photo_1, photo_2, photo_3], model='gemini-3.8-flash', config=LISTING_CONFIG
    )
    details = parse_details(response.candidates[0].content.parts[0].text.astype(pxt.String))
    ...
```

The app also does these things, each from a column or query in the same file, with no worker or sync script:

- Each listing gets an 11-second video made from its photos and narrated by Gemini.
- `/search` finds listings by their first photo from a description in words.
- `POST /ask` answers shoppers' questions. Gemini calls the app's `find_listings` query as a tool, Pixeltable runs the query, and Gemini picks from the results.
- `agent.py` does the same job as `POST /ask`, as a Pydantic AI agent. It reads the same listings table and returns the same `Picks` model, the list of listings chosen for the shopper.

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
Listings.where(Listings.details.condition == 'like new').select(Listings.title, Listings.price).collect()
```

With the 19 sample listings, the query returns four listings, e.g. `Black Adjustable LED Desk Lamp` at 45.0.

### 8. Search the photos in words

From the API:

```bash
curl "<url>/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
```

From the same Python shell:

```python
score = Listings.photo_1.similarity(string='warm light for a reading nook')
Listings.order_by(score, asc=False).limit(3).select(Listings.title, Listings.price, score=score).collect()
```

The `/search` route serves `search`, a query function in `app.py`. The Python code runs the same query directly.

### 9. Ask a question

```bash
curl -X POST <url>/ask -H 'content-type: application/json' \
  -d '{"question": "A like-new lamp under $100?"}'
```

The `/ask` response has its own `job_url`. Run `curl` on that `job_url` until `status` is `done`. The finished job's `result` has two parts:

- `picks`: Gemini's answer, as a `Picks` model. Its `picks` field lists the listings Gemini chose, each with a `why`, and its `note` field sums up the answer.
- `found`: the listings the `find_listings` query returned, which Gemini chose from. When we asked this question, Gemini called `find_listings` with `condition` set to `like new`, and the query returned only like-new listings.

Ask a question through the Pydantic AI agent:

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
pxt service update app.py market -f --otel
```

Post a listing as in step 3. In Logfire, the listing is a `pixeltable.insert` trace, with a span for each call Pixeltable made to fill the row's columns. Each span names its column. In one run, Gemini took 12.7 seconds to write `response`, 4.3 seconds to read the pitch into `narration`, and 1.6 seconds to embed the first photo for search. The `POST /listings` request is a separate trace, because the route returns a job before the insert runs.

`agent.py` sends its own traces to Logfire when `LOGFIRE_TOKEN` is set. Each Pixeltable query the agent runs shows up under the tool call that ran it.

To let a coding agent such as Claude Code read these traces, add the [Logfire MCP server](https://pydantic.dev/docs/logfire/guides/mcp-server/):

```bash
claude mcp add --transport http logfire https://logfire-us.pydantic.dev/mcp
claude mcp login logfire
```

## Files

- `app.py`: the app: the Pydantic models, the Pixeltable tables (`Listings` for listings, `Asks` for shoppers' questions), and the FastAPI routes, which Pixeltable's `FastAPIRouter` builds from the tables and queries. `pxt schema update` creates the tables from this file, and `pxt service update` serves the routes.
- `agent.py`: the Pydantic AI version of `POST /ask`. The agent searches and queries the listings table with tools from Pixeltable's add-on for Pydantic AI Harness, a package of add-ons for Pydantic AI agents. The add-on isn't released yet, so `pyproject.toml` installs the add-on from the branch of [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: runs 17 searches, each with a known right listing. `/search` ranks that listing first in all 17.
