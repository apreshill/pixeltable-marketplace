"""The whole marketplace: its Pydantic models, its tables, the AI that runs on them, and its API.

A seller sends three photos. Pixeltable checks each one is an image, a model writes the
listing into `ListingDetails`, and the photos become a narrated listing video. Buyers search
the listings by text or by photo.

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
from pixeltable.functions import huggingface, openai, video
from pixeltable.functions.uuid import uuid7
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


TableModel = pxt.model_base()

LISTING_FORMAT = {
    'type': 'json_schema',
    'json_schema': {'name': 'listing', 'schema': ListingDetails.model_json_schema()},
}
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
    response = openai.chat_completions(
        messages=[
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': PROMPT},
                    {'type': 'image_url', 'image_url': photo_1},
                    {'type': 'image_url', 'image_url': photo_2},
                    {'type': 'image_url', 'image_url': photo_3},
                ],
            }
        ],
        model='gpt-5.4-mini',
        model_kwargs={'response_format': LISTING_FORMAT},
    )
    details = parse_details(response.choices[0].message.content.astype(pxt.String))
    title = details.title.astype(pxt.String)
    description = details.description.astype(pxt.String)

    # The photos become a narrated listing video.
    narration = openai.speech(details.pitch.astype(pxt.String), model='tts-1', voice='alloy')
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
        pxt.EmbeddingIndex(photo_1, embedding=huggingface.clip.using(model_id='openai/clip-vit-base-patch32')),
        # Search the listings by what the model wrote about them.
        pxt.EmbeddingIndex(description, embedding=openai.embeddings.using(model='text-embedding-3-small')),
    ]


@pxt.query
def search(q: str, limit: int = 5):
    score = Listings.description.similarity(string=q)
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


api = FastAPI(title='Marketplace')
api.include_router(router)


@api.get('/listings/{listing_id}')
def get_listing(listing_id: UUID) -> Listing:
    """An ordinary FastAPI route that returns a row as the app's own Pydantic model."""
    listings = pxt.get_table('market.listings')
    rows = (
        listings.where(listings.id == listing_id)
        .select(listings.id, listings.seller, listings.price, listings.title, listings.details)
        .collect()
    )
    listing = next(rows.to_pydantic(Listing), None)
    if listing is None:
        raise HTTPException(status_code=404, detail='No such listing')
    return listing
