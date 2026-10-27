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

Here is the first of those steps in `app.py`, on a Pixeltable table class. A column with a type stores what the seller sends. A column set to a Pixeltable call, like `gemini.generate_content`, runs that call on every new row:

```python
class Listings(TableModel, name='listings'):
    id = pxt.Column(value=uuid7(), primary_key=True)
    seller: pxt.String
    price: pxt.Float
    photo_1: pxt.Image
    photo_2: pxt.Image
    photo_3: pxt.Image

    # Gemini writes the listing from the photos; parse_details() turns Gemini's JSON into a ListingDetails.
    response = gemini.generate_content(
        [PROMPT, photo_1, photo_2, photo_3], model='gemini-3.8-flash', config=LISTING_CONFIG
    )
    details = parse_details(response.candidates[0].content.parts[0].text.astype(pxt.String))
    ...
```

Shoppers can also ask a question, like "something warm to read by, under $150", and get matching listings back from `POST /ask`. Gemini calls the app's `find_listings` query as a tool, Pixeltable runs the query, and Gemini picks from the results. If your agents already run on Pydantic AI, `agent.py` does the same job as a Pydantic AI agent that reads the same listings table and returns the same `Picks` model.

## Run the app

You need Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg`, and `GEMINI_API_KEY` set in your environment. The `-f` flag skips the confirmation prompts.

```bash
uv sync
source .venv/bin/activate
pxt schema update app.py market -f   # create the tables in a local database named market
pxt service update app.py market -f  # start the app on localhost
pxt service list                     # print the app's URL
URL=http://127.0.0.1:PORT            # replace PORT with the port pxt service list printed
```

Post a listing with three photos and a price. Gemini writes the listing and Pixeltable makes the promo video, which takes about 15 seconds, so Pixeltable runs the insert as a background job. The POST answers right away with a job `id` and a `job_url` to poll.

```bash
curl -X POST $URL/listings -F seller=you -F price=260 \
  -F photo_1=@samples/guitar-1.jpg -F photo_2=@samples/guitar-2.jpg -F photo_3=@samples/guitar-3.jpg
curl JOB_URL   # the job_url from the response; "status" goes from "pending" to "done" (or "error")
```

When the job is done, the job's `result` has the listing's `id` (not the job id), the `details` Gemini wrote, and a link to the `promo` video.

Look at what Pixeltable stored:

```bash
pxt get market/listings ID --cols title,price,details,promo   # the new row; ID is the id in the job's result
pxt rows market/listings --cols title,price                   # every listing so far
pxt errors market/listings                                     # rows where a Gemini call or the promo video failed
pxt dashboard                                                  # open the Pixeltable dashboard
```

Post the 19 sample listings, then call `/search` and `/ask`:

```bash
python scripts/seed.py $URL
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by, under $150?"}'   # also returns a job_url; the answer is in "result"
python agent.py "Something warm to read by, under \$150?"   # the same question, answered by the Pydantic AI agent
```

## Files

- `app.py`: the app: the Pydantic models, the Pixeltable tables (`Listings` for listings, `Asks` for shoppers' questions), and the FastAPI routes, which Pixeltable's `FastAPIRouter` builds from the tables and queries. `pxt schema update` creates the tables from this file, and `pxt service update` serves the routes.
- `agent.py`: the Pydantic AI version of `POST /ask`. The agent searches and queries the listings table with tools from Pixeltable's add-on for Pydantic AI Harness, a package of add-ons for Pydantic AI agents. The add-on isn't released yet, so `pyproject.toml` installs the add-on from the branch of [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- `scripts/seed.py`: posts the sample listings
- `scripts/search_test.py`: runs 17 searches, each with a known right listing. `/search` ranks that listing first in all 17.
