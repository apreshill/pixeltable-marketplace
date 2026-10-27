# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, where [Pixeltable](https://github.com/pixeltable/pixeltable) is the database and runs the AI on the photos.

A seller posts three photos and a price. In one request:

- each photo is checked as an image when it's inserted, so a PDF or a video renamed `.jpg` gets a 422
- a model reads the photos and writes the listing into the app's own Pydantic model, `ListingDetails`
- the photos become a 10-second listing video, with narration, the title, and the price
- the listing becomes searchable by what its photos show

Buyers search the listings, or ask a buyer's agent. The agent is built two ways, side by side, and both read the same table and return the same Pydantic model, `Picks`.

## The two buyer's agents

| | `POST /ask`, in `app.py` | `agent.py` |
|---|---|---|
| Built with | Pixeltable alone | Pydantic AI, with the Pixeltable capability for Pydantic AI Harness |
| Where it runs | In the app, as a route | As its own program, next to the app |
| How it searches | Gemini calls the app's own query, `find_listings`, through `pxt.tools()`, and Pixeltable runs it | The agent calls the Harness tools (`list_tables`, `describe_table`, `query_table`, `similarity_search`) on `market.listings` |
| Where its work is kept | In the `asks` table: each question is a row, and the tool call, what the search found, and the picks are its columns | In the agent's run, and in Logfire when `LOGFIRE_TOKEN` is set |
| Use it when | You're building the app on Pixeltable and want the agent to be part of it | You already run agents in Pydantic AI and want one to read your Pixeltable tables |

The `asks` table, from `app.py`:

```python
TOOLS = pxt.tools(find_listings)  # find_listings is the app's own @pxt.query

class Asks(TableModel, name='asks'):
    id = pxt.Column(value=uuid7(), primary_key=True)
    question: pxt.String

    # Gemini decides how to call the app's own query, and Pixeltable runs the call.
    tool_call = gemini.generate_content(question, model='gemini-3.8-flash', tools=TOOLS, config=...)
    found = gemini.invoke_tools(TOOLS, tool_call)
    # Gemini picks from what the query found, into the app's own Pydantic model.
    answer = gemini.generate_content(question + PICK_INSTRUCTIONS + json.dumps(found), model='gemini-3.8-flash', config=PICKS_CONFIG)
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

## What's where

- `app.py` is the whole app: the Pydantic models, the `listings` and `asks` tables, the model calls and video steps that run on each new row, the search index, and the FastAPI app with its routes.
- `agent.py` is the Pydantic AI buyer's agent. It imports `Listings` and `Picks` from `app.py`.
- `scripts/seed.py` posts the 19 sample listings.
- `scripts/search_test.py` runs 17 buyer searches whose right answers are written down, and counts how many put the right listing first. Most sample listings have near misses: lamps, bags, and bikes that differ on the point a buyer searches for.

## Run it

Needs Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg` on your PATH, and `GEMINI_API_KEY` in your environment.

```bash
uv sync
uv run pxt schema update app.py market -f
uv run pxt service update app.py market -f
uv run pxt service list
```

`pxt service list` prints the app's URL. With that URL as `$URL`:

```bash
uv run python scripts/seed.py $URL
uv run python scripts/search_test.py $URL
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/similar -F photo=@samples/road-bike-3.jpg
```

Ask the buyer's agent both ways:

```bash
curl -X POST $URL/ask -H 'content-type: application/json' \
  -d '{"question": "Something warm to read by in my living room, under $150?"}'
uv run python agent.py "Something warm to read by in my living room, under \$150?"
```

To post your own listing:

```bash
curl -X POST $URL/listings -F seller=you -F price=120 \
  -F photo_1=@front.jpg -F photo_2=@back.jpg -F photo_3=@detail.jpg
```

Every AI step runs on Gemini: `gemini-3.8-flash` writes the listing and runs both agents, `gemini-3.8-flash-tts` reads the narration, and `gemini-embedding-2` indexes the photos and the descriptions. A listing took about 14 seconds in our runs.

## Notes

- `/search` searches the photos, not the descriptions Gemini writes. On the 17 test searches, the photos put the right listing first 17 times and the descriptions 10 times.
- The sample photos were generated with image models (OpenAI's `gpt-image-1-mini` for nine listings, Gemini's `gemini-3.1-flash-image` for the other ten), to get three matching angles of each item. Use your own photos to try it on real listings.
- The Pixeltable capability for Pydantic AI Harness is not released yet. `pyproject.toml` installs it, and the `pydantic-ai-slim` it needs, from [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- Logfire prints the Pydantic AI agent's trace in your terminal. Set `LOGFIRE_TOKEN` to send it to Logfire.
