"""A buyer's assistant over the marketplace's listings: python agent.py "what are you looking for?" """

import sys
from uuid import UUID

import logfire
import pixeltable as pxt
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai_harness import Pixeltable

logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()


class Pick(BaseModel):
    listing_id: UUID
    title: str
    price: float
    why: str


class Picks(BaseModel):
    picks: list[Pick]
    note: str


agent = Agent(
    'openai:gpt-5.4-mini',
    output_type=Picks,
    instructions=(
        'You help buyers on a secondhand marketplace. Search the listings, and recommend only '
        'listings that fit what the buyer asked for, with their real id, title, and price. '
        'An empty list is a fine answer: say so in the note when nothing fits.'
    ),
    capabilities=[Pixeltable(['market.listings'])],
)


@agent.output_validator
def picks_are_listed(output: Picks) -> Picks:
    """Every pick must be a real listing at its real price."""
    listings = pxt.get_table('market.listings')
    for pick in output.picks:
        rows = listings.where(listings.id == pick.listing_id).select(listings.price).collect()
        if len(rows) == 0:
            raise ModelRetry(f'{pick.listing_id} is not a listing id. Query the listing and use its id.')
        if rows[0]['price'] != pick.price:
            raise ModelRetry(f"Listing {pick.listing_id} costs {rows[0]['price']}, not {pick.price}.")
    return output


if __name__ == '__main__':
    question = sys.argv[1] if len(sys.argv) > 1 else 'Something for a cozy reading corner, under $150?'
    result = agent.run_sync(question)
    print(result.output.model_dump_json(indent=2))
