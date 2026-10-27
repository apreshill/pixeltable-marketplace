"""The app's own Pydantic models. Pixeltable uses them as they are."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
