"""The marketplace's FastAPI app. Run it with: uvicorn main:api --reload"""

from uuid import UUID

import pixeltable as pxt
from fastapi import FastAPI, HTTPException

import app
from models import Listing

api = FastAPI(title='Marketplace')

# Pixeltable's routes: create a listing, search by text, search by photo.
app.router.bind('market')
api.include_router(app.router)


@api.get('/listings/{listing_id}')
def get_listing(listing_id: UUID) -> Listing:
    """An ordinary FastAPI route that reads a row back as the app's own Pydantic model."""
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
