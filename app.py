"""The whole marketplace: its Pydantic models, its tables, the AI that runs on them, and its API.

A seller sends three photos. Pixeltable checks each one is an image, a model writes the
listing into `ListingDetails`, and the photos become a narrated listing video. Buyers search
the listings by text or by photo, or ask the buyer's agent, which is a table too: each question
is a row, and Gemini answers it by calling the app's own query as a tool (`pxt.tools`).

The same table also works with Pydantic AI: see agent.py.

    pxt schema update app.py market -f
    pxt service update app.py market -f
"""

import tempfile
from typing import Literal
from uuid import UUID

import av
import PIL.Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import pixeltable as pxt
from pixeltable.functions import gemini, json, video
from pixeltable.functions.uuid import to_string, uuid7
from pixeltable.serving import FastAPIRouter


class ListingDetails(BaseModel):
    """What the model writes from a seller's photos."""

    title: str = Field(description='A listing title, under 60 characters')
    category: Literal['cameras', 'bikes', 'home', 'bags', 'instruments', 'other']
    condition: Literal['new', 'like new', 'good', 'fair']
    color: str
    description: str = Field(description='Two or three sentences for buyers, about only what the photos show')
    pitch: str = Field(description='Narration for a 10-second listing video: two short spoken sentences, 15 to 25 words')


class Listing(BaseModel):
    """A listing as the storefront shows it."""

    id: UUID
    seller: str
    price: float
    title: str
    details: ListingDetails


class Pick(BaseModel):
    listing_id: UUID
    title: str
    price: float
    why: str = Field(description='Why this listing fits what the buyer asked for, in one sentence')


class Picks(BaseModel):
    """The buyer's agent's answer. Both agents return it: the one in this file and agent.py."""

    picks: list[Pick] = Field(description='Only listings that fit; an empty list when none do')
    note: str = Field(description='One or two sentences to the buyer')


TableModel = pxt.model_base()

LISTING_CONFIG = {'response_mime_type': 'application/json', 'response_json_schema': ListingDetails.model_json_schema()}
PROMPT = 'Write a marketplace listing for the item in these photos. Describe only what the photos show.'


@pxt.udf
def parse_details(raw: str) -> pxt.Json[ListingDetails]:
    return ListingDetails.model_validate_json(raw).model_dump()


@pxt.udf
def still(image: PIL.Image.Image, seconds: float = 4.0) -> pxt.Video:
    """A video that holds one photo for `seconds`."""
    size, fps = 720, 24
    path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    frame = av.VideoFrame.from_image(image.convert('RGB').resize((size, size)))
    with av.open(path, 'w') as out:
        stream = out.add_stream('libx264', rate=fps)
        stream.width, stream.height, stream.pix_fmt = size, size, 'yuv420p'
        for _ in range(int(seconds * fps)):
            out.mux(stream.encode(frame))
        out.mux(stream.encode())
    return path


@pxt.udf
def caption(title: str, price: float) -> str:
    return f'{title}  ${price:,.0f}'


def slow_zoom(photo: pxt.exprs.Expr, zoom_in: bool) -> pxt.exprs.Expr:
    start, end = (1.0, 1.12) if zoom_in else (1.12, 1.0)
    return video.zoom(still(photo), start_scale=start, end_scale=end)


class Listings(TableModel, name='listings'):
    id = pxt.Column(value=uuid7(), primary_key=True)
    seller: pxt.String
    price: pxt.Float
    photo_1: pxt.Image
    photo_2: pxt.Image
    photo_3: pxt.Image

    # A model writes the listing from the photos, into the app's own Pydantic model.
    response = gemini.generate_content(
        [PROMPT, photo_1, photo_2, photo_3], model='gemini-3.8-flash', config=LISTING_CONFIG
    )
    details = parse_details(response.candidates[0].content.parts[0].text.astype(pxt.String))
    title = details.title.astype(pxt.String)
    description = details.description.astype(pxt.String)

    # The photos become a narrated listing video.
    narration = gemini.generate_speech(details.pitch.astype(pxt.String), model='gemini-3.8-flash-tts', voice='Kore')
    slideshow = video.transition(
        video.transition(slow_zoom(photo_1, True), slow_zoom(photo_2, False), effect='fade', duration=0.6),
        slow_zoom(photo_3, True),
        effect='fade',
        duration=0.6,
    )
    promo = video.with_audio(
        video.overlay_text(
            slideshow, caption(title, price), font_size=30, color='white', horizontal_align='center',
            box=True, box_color='black', box_opacity=0.6, vertical_align='bottom', vertical_margin=36,
        ),
        narration,
    )

    __indexes__ = [
        # Search the listings by photo, or by words that describe one.
        pxt.EmbeddingIndex(photo_1, embedding=gemini.embed_content.using(model='gemini-embedding-2')),
        # Search the listings by what the model wrote about them.
        pxt.EmbeddingIndex(description, embedding=gemini.embed_content.using(model='gemini-embedding-2')),
    ]


@pxt.query
def search(q: str, limit: int = 5):
    # Search the photos, not the description: a photo shows what a description leaves out, like
    # the color of a lamp's light (scripts/search_test.py: 17 of 17 searches, against 10 of 17).
    score = Listings.photo_1.similarity(string=q)
    return (
        Listings.order_by(score, asc=False)
        .limit(limit)
        .select(Listings.id, Listings.title, Listings.price, Listings.photo_1, score=score)
    )


@pxt.query
def similar(photo: pxt.Image, limit: int = 5):
    score = Listings.photo_1.similarity(image=photo)
    return (
        Listings.order_by(score, asc=False)
        .limit(limit)
        .select(Listings.id, Listings.title, Listings.price, Listings.photo_1, score=score)
    )


@pxt.query
def find_listings(looking_for: str, max_price: float):
    """Find listings whose photos match what the buyer is looking for, at or under max_price.

    Args:
        looking_for: What the buyer wants, in their words, without the price.
        max_price: The most the buyer will pay, in dollars. When they don't say, use 100000.
    """
    score = Listings.photo_1.similarity(string=looking_for)
    return (
        Listings.where(Listings.price <= max_price)
        .order_by(score, asc=False)
        .limit(5)
        .select(listing_id=to_string(Listings.id), title=Listings.title, price=Listings.price,
                description=Listings.description, score=score)
    )


TOOLS = pxt.tools(find_listings)
ASK_INSTRUCTIONS = 'You help buyers on a secondhand marketplace. Call find_listings to search the listings.'
PICK_INSTRUCTIONS = (
    '\n\nRecommend only the listings that fit what the buyer asked for, with their listing_id, title, and '
    'price exactly as found. An empty list is a fine answer.\n\nListings the search found: '
)
PICKS_CONFIG = {'response_mime_type': 'application/json', 'response_json_schema': Picks.model_json_schema()}


@pxt.udf
def parse_picks(raw: str) -> pxt.Json[Picks]:
    return Picks.model_validate_json(raw).model_dump(mode='json')


class Asks(TableModel, name='asks'):
    """The buyer's agent: each question is a row, and every step of the answer is a column."""

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


router = FastAPIRouter(name='market')
router.add_insert_route(
    Listings,
    path='/listings',
    inputs=[Listings.seller, Listings.price],
    uploadfile_inputs=[Listings.photo_1, Listings.photo_2, Listings.photo_3],
    outputs=[Listings.id, Listings.title, Listings.details, Listings.promo],
)
router.add_query_route(path='/search', query=search, method='get')
router.add_query_route(path='/similar', query=similar, uploadfile_inputs=['photo'])
router.add_insert_route(Asks, path='/ask', inputs=[Asks.question], outputs=[Asks.id, Asks.found, Asks.picks])


api = FastAPI(title='Marketplace')
api.include_router(router)


@api.get('/listings/{listing_id}')
def get_listing(listing_id: UUID) -> Listing:
    """An ordinary FastAPI route that returns a row as the app's own Pydantic model."""
    rows = (
        Listings.where(Listings.id == listing_id)
        .select(Listings.id, Listings.seller, Listings.price, Listings.title, Listings.details)
        .collect()
    )
    listing = next(rows.to_pydantic(Listing), None)
    if listing is None:
        raise HTTPException(status_code=404, detail='No such listing')
    return listing
