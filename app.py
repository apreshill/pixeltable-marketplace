"""A secondhand marketplace on Pixeltable: the Pydantic models, the listings table, and its API.

A seller posts three photos and a price. Gemini writes the listing's details, which must validate
against `ListingDetails`; Gemini finds the item in the first photo for a crop; and the photos become
a narrated video. Shoppers search the photos in words or with a photo. agent.py is a Pydantic AI
agent over the same table.

    pxt schema update app.py market
    pxt service update app.py market
"""

import tempfile
from pathlib import Path
from typing import Literal
from uuid import UUID

import av
import PIL.Image
import PIL.ImageOps
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import pixeltable as pxt
import pixeltable.functions as pxtf
from pixeltable.serving import FastAPIRouter

MODEL = 'gemini-3.8-flash'
TTS_MODEL = 'gemini-3.8-flash-tts'
EMBEDDING_MODEL = 'gemini-embedding-2'

Condition = Literal['new', 'like new', 'good', 'fair']


class ListingDetails(BaseModel):
    """What Gemini writes from a seller's photos."""

    title: str = Field(description='A listing title, under 60 characters')
    category: Literal['cameras', 'bikes', 'home', 'bags', 'instruments', 'other']
    condition: Condition
    color: str
    description: str = Field(description='Two or three sentences for buyers, about only what the photos show')
    pitch: str = Field(description='Narration for a 10-second listing video: two short spoken sentences, 15 to 25 words')


class Box(BaseModel):
    """Where the item is in a photo, on a 0 to 1000 scale."""

    ymin: int = Field(ge=0, le=1000)
    xmin: int = Field(ge=0, le=1000)
    ymax: int = Field(ge=0, le=1000)
    xmax: int = Field(ge=0, le=1000)


class Listing(BaseModel):
    """A listing as the storefront shows it."""

    id: UUID
    seller: str
    price: float
    title: str
    details: ListingDetails


TableModel = pxt.model_base()

DETAILS_PROMPT = 'Write a marketplace listing for the item in these photos. Describe only what the photos show.'
BOX_PROMPT = (
    'Return the bounding box of this item in the photo. If the item is not visible, or most of it is hidden, '
    'return the whole photo: ymin 0, xmin 0, ymax 1000, xmax 1000. Item:'
)


def json_config(model: type[BaseModel]) -> dict:
    """Gemini config that asks for JSON in the shape of `model`."""
    return {'response_mime_type': 'application/json', 'response_json_schema': model.model_json_schema()}


def gemini_text(response: pxt.exprs.Expr) -> pxt.exprs.Expr:
    """The text of a Gemini response."""
    return response.candidates[0].content.parts[0].text.astype(pxt.String)


@pxt.udf
def parse_details(raw: str) -> pxt.Json[ListingDetails]:
    return ListingDetails.model_validate_json(raw).model_dump()


@pxt.udf
def parse_box(raw: str) -> pxt.Json[Box]:
    return Box.model_validate_json(raw).model_dump()


@pxt.udf
def crop_to_box(photo: PIL.Image.Image, box: pxt.Json[Box], margin: float = 0.08) -> PIL.Image.Image:
    """Crop `photo` to `box`, with `margin` of the box's size added on each side, within the photo."""
    b = Box.model_validate(box)
    width, height = photo.size
    pad_x, pad_y = (b.xmax - b.xmin) * margin, (b.ymax - b.ymin) * margin
    left = max(0.0, b.xmin - pad_x) * width / 1000
    top = max(0.0, b.ymin - pad_y) * height / 1000
    right = min(1000.0, b.xmax + pad_x) * width / 1000
    bottom = min(1000.0, b.ymax + pad_y) * height / 1000
    if right - left < 1 or bottom - top < 1:
        return photo  # an empty box: keep the whole photo
    return photo.crop((round(left), round(top), round(right), round(bottom)))


@pxt.udf
def still(image: PIL.Image.Image, seconds: float = 4.0) -> pxt.Video:
    """A square video that holds one photo for `seconds`, padded rather than stretched.

    Pixeltable ships no function that turns one image into a video, so this encodes one with PyAV. The file
    goes in a new temp directory, which Pixeltable moves into its media store.
    """
    size, fps = 720, 24
    path = Path(tempfile.mkdtemp()) / 'still.mp4'
    frame = av.VideoFrame.from_image(PIL.ImageOps.pad(image.convert('RGB'), (size, size)))
    with av.open(str(path), 'w') as out:
        stream = out.add_stream('libx264', rate=fps)
        stream.width, stream.height, stream.pix_fmt = size, size, 'yuv420p'
        for _ in range(int(seconds * fps)):
            out.mux(stream.encode(frame))
        out.mux(stream.encode())
    return str(path)


def slow_zoom(photo: pxt.exprs.Expr, zoom_in: bool) -> pxt.exprs.Expr:
    start, end = (1.0, 1.12) if zoom_in else (1.12, 1.0)
    return pxtf.video.zoom(still(photo), start_scale=start, end_scale=end)


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
    category = details.category.astype(pxt.String)
    condition = details.condition.astype(pxt.String)
    color = details.color.astype(pxt.String)
    description = details.description.astype(pxt.String)
    pitch = details.pitch.astype(pxt.String)

    # The item's box in the first photo, validated against Box, and the photo cropped to it.
    box_response = pxtf.gemini.generate_content([BOX_PROMPT, title, photo_1], model=MODEL, config=json_config(Box))
    box = parse_box(gemini_text(box_response))
    cropped_photo = crop_to_box(photo_1, box)

    # A narrated video: the three photos with slow zooms, the title and price as a caption, and the pitch read aloud.
    narration = pxtf.gemini.generate_speech(pitch, model=TTS_MODEL, voice='Kore')
    slideshow = pxtf.video.transition(
        pxtf.video.transition(slow_zoom(photo_1, True), slow_zoom(photo_2, False), effect='fade', duration=0.6),
        slow_zoom(photo_3, True),
        effect='fade',
        duration=0.6,
    )
    promo = pxtf.video.with_audio(
        pxtf.video.overlay_text(
            slideshow, pxtf.string.format('{}  ${}', title, pxtf.math.to_int(price)), font_size=30, color='white',
            horizontal_align='center', box=True, box_color='black', box_opacity=0.6, vertical_align='bottom',
            vertical_margin=36,
        ),
        narration,
    )

    __indexes__ = [
        # Search by the first photo, from words or from another photo.
        pxt.EmbeddingIndex(photo_1, embedding=pxtf.gemini.embed_content.using(model=EMBEDDING_MODEL)),
        pxt.BtreeIndex(condition),
    ]


@pxt.query
def search(q: str, condition: str | None = None, limit: int = 5):
    """Listings whose first photo best matches `q`, optionally only those in `condition`."""
    score = Listings.photo_1.similarity(string=q)
    return (
        Listings.where((condition == None) | (Listings.condition == condition))  # noqa: E711
        .order_by(score, asc=False)
        .limit(limit)
        .select(Listings.id, Listings.title, Listings.price, Listings.condition, Listings.photo_1, score=score)
    )


@pxt.query
def similar(photo: pxt.Image, limit: int = 5):
    """Listings whose first photo looks most like `photo`."""
    score = Listings.photo_1.similarity(image=photo)
    return (
        Listings.order_by(score, asc=False)
        .limit(limit)
        .select(Listings.id, Listings.title, Listings.price, Listings.condition, Listings.photo_1, score=score)
    )


router = FastAPIRouter(name='market')
router.add_insert_route(
    Listings,
    path='/listings',
    inputs=[Listings.seller, Listings.price],
    uploadfile_inputs=[Listings.photo_1, Listings.photo_2, Listings.photo_3],
    outputs=[Listings.id, Listings.title, Listings.details, Listings.cropped_photo, Listings.promo],
    background=True,  # the Gemini calls and the video take about 15 seconds
)
router.add_query_route(path='/search', query=search, method='get')
router.add_query_route(path='/similar', query=similar, uploadfile_inputs=['photo'])


api = FastAPI(title='Marketplace')
api.include_router(router)


@api.get('/listings/{listing_id}')
def get_listing(listing_id: UUID) -> Listing:
    # A query route returns columns; this handler returns the app's own Listing model, which a route can't.
    rows = (
        Listings.where(Listings.id == listing_id)
        .select(Listings.id, Listings.seller, Listings.price, Listings.title, Listings.details)
        .collect()
    )
    listing = next(rows.to_pydantic(Listing), None)
    if listing is None:
        raise HTTPException(status_code=404, detail='No such listing')
    return listing
