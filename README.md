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

Two small clients sit next to it: `agent.py`, a buyer's assistant built with Pydantic AI, and `scripts/seed.py`, which posts the five sample listings.

## Run it

Needs Python 3.12 to 3.14, [uv](https://docs.astral.sh/uv/), `ffmpeg` on your PATH, and `OPENAI_API_KEY` in your environment.

```bash
uv sync
uv run pxt schema update app.py market -f
uv run pxt service update app.py market -f
uv run pxt service list
```

`pxt service list` prints the app's URL. With that URL as `$URL`:

```bash
uv run python scripts/seed.py $URL
curl "$URL/search?q=warm%20light%20for%20a%20reading%20nook&limit=3"
curl -X POST $URL/similar -F photo=@samples/road-bike-3.jpg
uv run python agent.py "I bike to work and need something to carry my laptop. Anything under \$200?"
```

To post your own listing:

```bash
curl -X POST $URL/listings -F seller=you -F price=120 \
  -F photo_1=@front.jpg -F photo_2=@back.jpg -F photo_3=@detail.jpg
```

Each listing makes three OpenAI calls (`gpt-5.4-mini` for the listing, `tts-1` for the narration, `text-embedding-3-small` for search) and took about 10 seconds in our runs. Photo search uses CLIP, which runs locally.

## Notes

- The sample photos were generated with OpenAI's image model (`gpt-image-1-mini`), to get three matching angles of each item. Use your own photos to try it on real listings.
- The Pixeltable capability for Pydantic AI Harness is not released yet. `pyproject.toml` installs it, and the `pydantic-ai-slim` it needs, from [pydantic/pydantic-ai#9369](https://github.com/pydantic/pydantic-ai/pull/9369).
- Logfire prints the agent's trace in your terminal. Set `LOGFIRE_TOKEN` to send it to Logfire.
