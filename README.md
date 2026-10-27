# pixeltable-marketplace

A secondhand marketplace built with FastAPI and Pydantic, where [Pixeltable](https://github.com/pixeltable/pixeltable) is the database and runs the AI on the photos.

A seller posts three photos and a price. In one request:

- each photo is checked as an image when it's inserted, so a PDF or a video renamed `.jpg` gets a 422
- a model reads the photos and writes the listing into the app's own Pydantic model, `ListingDetails`
- the photos become a 10-second listing video, with narration, the title, and the price
- the listing becomes searchable by text and by photo

A buyer's agent, built with Pydantic AI, searches the same table.

## What's where

`app.py` is the whole app: the Pydantic models, the `listings` table, the model calls and video steps that run on each new row, the search indexes, and the FastAPI app with its routes.

Small clients sit next to it: `agent.py`, a buyer's assistant built with Pydantic AI; `scripts/seed.py`, which posts the 19 sample listings; and `scripts/search_test.py`, which runs 17 buyer searches whose right answers are written down and counts how many put the right listing first. Most sample listings have near misses: lamps, bags, and bikes that differ on the point a buyer searches for.

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
uv run python agent.py "I bike to work and need something to carry my laptop. Anything under \$200?"
```

To post your own listing:

```bash
curl -X POST $URL/listings -F seller=you -F price=120 \
  -F photo_1=@front.jpg -F photo_2=@back.jpg -F photo_3=@detail.jpg
```

Every AI step runs on Gemini: `gemini-3.8-flash` writes the listing, `gemini-3.8-flash-tts` reads the narration, and `gemini-embedding-2` indexes both the photos and the descriptions for search. A listing took about 14 seconds in our runs.

## Notes

- The sample photos were generated with image models (OpenAI's `gpt-image-1-mini` for the first ten listings, Gemini's `gemini-3.1-flash-image` for the rest), to get three matching angles of each item. Use your own photos to try it on real listings.
- The Pixeltable capability for Pydantic AI Harness is not released yet. `pyproject.toml` installs it, and the `pydantic-ai-slim` it needs, from [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- Logfire prints the agent's trace in your terminal. Set `LOGFIRE_TOKEN` to send it to Logfire.
