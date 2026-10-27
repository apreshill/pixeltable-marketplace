# pixeltable-marketplace

A secondhand marketplace where [Pixeltable](https://github.com/pixeltable/pixeltable) is the backend. It stores the listings and their photos, runs Gemini on each new listing, and turns its tables into FastAPI routes. The models are Pydantic, as you'd expect; Pixeltable is the part you'd otherwise build out of Postgres, a bucket of files, a worker queue, and a vector database.

When a seller posts three photos and a price, Pixeltable:

- opens each photo before it stores the row, so a PDF renamed `.jpg` is refused with a 422
- sends the three photos to Gemini and stores the listing it writes as your Pydantic model, `ListingDetails`
- turns the photos into a 10-second listing video with narration, the title, and the price
- indexes the main photo, so a buyer finds the listing by what's in it

In `app.py`, those four steps are the `Listings` class: column types, computed columns, and an index. Pixeltable runs them on every new listing. You don't write the upload check, the worker that calls Gemini, or the script that keeps the search index current.

Pixeltable also runs the buyer's agent, as a second table. Each question is a row in `asks`: Gemini calls the app's own search query as a tool, Pixeltable runs the call, and the answer comes back as your Pydantic model, `Picks`. Every step stays on the row, so you can query what the agent searched for and what it found.

If your agents already run on Pydantic AI, `agent.py` connects one to the `listings` table with Pixeltable's capability for Pydantic AI Harness.

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
