# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, with [Pixeltable](https://github.com/pixeltable/pixeltable) as its database. Pixeltable stores the listings and their photos, runs Gemini on each new listing, keeps the photo search up to date, and turns its tables into routes that the FastAPI app includes. It takes the place of the Postgres database, S3 bucket, worker queue, and vector database you would otherwise wire together.

```
Without Pixeltable                         With Pixeltable

FastAPI + Pydantic                         FastAPI + Pydantic
   │                                          │
   ├─ Postgres: rows and file paths           └─ Pixeltable, declared in app.py:
   ├─ S3: the photos                               rows and photos, the image check,
   ├─ code that checks each file is an image       Gemini on every new listing,
   ├─ a worker queue: calls Gemini,                the listing video, the photo search
   │    makes the listing video
   └─ a vector database, plus the script
        that keeps it in sync
```

When a seller posts three photos and a price, Pixeltable:

- checks that each photo is an image before it stores the row, so a PDF renamed `.jpg` gets a 422
- sends the photos to Gemini, which writes a title, category, condition, color, description, and short pitch, and checks them against your Pydantic model, `ListingDetails`
- makes a 10-second video from the photos, with Gemini's voice reading the pitch and the title and price on screen
- adds the first photo to the search, so a shopper can describe what they want in words and find it

All four steps are declared once, on the `Listings` class in `app.py`, and Pixeltable runs them for every new listing.

Shoppers can also ask a question in a sentence and get matching listings back, from `POST /ask`. Pixeltable stores each question as a row. Gemini decides how to call the app's `find_listings` query, Pixeltable runs that query, and Gemini picks from the results, checked against your Pydantic model, `Picks`. The query call, the listings it found, and the answer are all saved in the question's row, so you can look up what any answer was based on.

If you build agents with Pydantic AI, `agent.py` shows the same thing from that side: Pixeltable gives a Pydantic AI agent tools to list, describe, query, and search the `listings` table, and the agent answers with the same `Picks` model.

## What's where

- `app.py` is the whole app: the Pydantic models, the table of listings and the table of shoppers' questions, the Gemini calls and video steps that run on each new row, the photo search, and the FastAPI app with its routes.
- `agent.py` is the Pydantic AI agent that answers the same questions as `POST /ask`. It imports `Listings` and `Picks` from `app.py`.
- `scripts/seed.py` posts the 19 sample listings.
- `scripts/search_test.py` runs 17 shopper searches, each with one listing that should come first, and counts how many times `/search` puts it first. 17 of the 19 sample listings are lamps, bags, or bikes that differ in the detail a search names, such as warm light or bright white light, so a search has to pick the right one.

## Run it

Needs Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg` on your PATH, and `GEMINI_API_KEY` in your environment. There is no Postgres, S3 bucket, worker, or vector database to start, and no Pixeltable account to create.

`pxt schema update` creates the tables declared in `app.py` in a local Pixeltable database, under the name `market` (so the listings table is `market.listings`). `pxt service update` starts the app on localhost, and `pxt service list` prints its URL. `-f` applies each change without asking you to confirm it.

```bash
uv sync
uv run pxt schema update app.py market -f
uv run pxt service update app.py market -f
uv run pxt service list
```

Copy the URL it prints into a shell variable, `URL`. Then post the sample listings, score the search, and try a search by words (`/search`) and by a photo (`/similar`):

```bash
uv run python scripts/seed.py $URL
uv run python scripts/search_test.py $URL
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/similar -F photo=@samples/road-bike-3.jpg
```

`seed.py` posts the listings one at a time. In our runs each `POST /listings` returned in about 14 seconds, after Gemini had written the listing and the video was made.

To post your own listing:

```bash
curl -X POST $URL/listings -F seller=you -F price=120 \
  -F photo_1=@front.jpg -F photo_2=@back.jpg -F photo_3=@detail.jpg
```

## Two ways to answer a shopper's question

The app answers a shopper's question in two ways. Both use Gemini, and both answer with the same Pydantic model, `Picks`. Ask the same question both ways:

```bash
curl -X POST $URL/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by in my living room, under $150?"}'
uv run python agent.py "Something warm to read by in my living room, under \$150?"
```

| | `POST /ask`, in `app.py` | `agent.py` |
|---|---|---|
| How it runs | As a route in the app. No agent framework: Pixeltable runs the Gemini calls. | As its own Python program, with Pydantic AI and Pixeltable's add-on for Pydantic AI Harness (not released yet; installed from [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369)) |
| How it finds listings | Gemini decides how to call `find_listings`, a query in `app.py` that matches the shopper's words against the listing photos, at or under a price. Pixeltable runs the call. | The agent queries and searches `market.listings` with the tools the add-on gives it. |
| Where you see what it did | In the app's database: one row per question | In a trace printed in your terminal, and in Logfire, Pydantic's observability service, when `LOGFIRE_TOKEN` is set |

How `POST /ask` saves each question, from `app.py`. `TOOLS` wraps `find_listings` for Gemini; `ASK_INSTRUCTIONS`, `PICK_INSTRUCTIONS`, `PICKS_CONFIG`, and `parse_picks` are defined just above the class.

```python
class Asks(TableModel, name='asks'):
    id = pxt.Column(value=uuid7(), primary_key=True)
    question: pxt.String

    # Gemini decides how to call the app's own query, and Pixeltable runs the call.
    tool_call = gemini.generate_content(
        question, model='gemini-3.8-flash', tools=TOOLS, config={'system_instruction': ASK_INSTRUCTIONS}
    )
    found = gemini.invoke_tools(TOOLS, tool_call)
    # Gemini picks from what the query found, into the app's own Pydantic model.
    answer = gemini.generate_content(
        question + PICK_INSTRUCTIONS + json.dumps(found), model='gemini-3.8-flash', config=PICKS_CONFIG
    )
    picks = parse_picks(answer.candidates[0].content.parts[0].text.astype(pxt.String))
```

The Pydantic AI agent, from `agent.py`:

```python
agent = Agent(
    'google:gemini-3.8-flash',
    output_type=Picks,
    instructions='You help buyers on a secondhand marketplace. ...',
    capabilities=[Pixeltable(['market.listings'])],
)
```

## Notes

- Every AI step runs on Gemini: `gemini-3.8-flash` writes the listing and is the model behind both ways of answering questions, `gemini-3.8-flash-tts` reads the narration, and `gemini-embedding-2` indexes the photos and the descriptions.
- `/search` searches the photos, not the descriptions Gemini writes. On the 17 test searches, searching the photos put the right listing first 17 times, and searching the descriptions did 10 times. `app.py` still builds the description index, but no route uses it.
- The sample photos were generated with image models, so each item has three matching angles. OpenAI's `gpt-image-1-mini` made nine listings, and Gemini's `gemini-3.1-flash-image` made the other ten. Use your own photos to try the app on real listings.
- `pyproject.toml` installs the unreleased Pixeltable add-on, and the `pydantic-ai-slim` it needs, from the branch of pydantic/pydantic-ai#9369.
