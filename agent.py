"""A buyer's agent built with Pydantic AI: python agent.py "what are you looking for?"

The agent searches and queries the app's listings table through the Pixeltable capability for
Pydantic AI Harness, and answers as `Picks`. Its output validator checks each pick against the table.
It keeps its notes across runs in a second Pixeltable table, `market.memory`.
"""

import sys
from uuid import UUID

import logfire
from opentelemetry.instrumentation.pixeltable import PixeltableInstrumentor
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai_harness import Memory, Pixeltable
from pydantic_ai_harness.memory import PixeltableMemoryStore

from app import MODEL, Listings, TableModel


class Pick(BaseModel):
    listing_id: UUID
    title: str
    price: float
    why: str = Field(description='Why this listing fits what the buyer asked for, in one sentence')


class Picks(BaseModel):
    picks: list[Pick] = Field(description='Only listings that fit; an empty list when none do')
    note: str = Field(description='One or two sentences to the buyer')


# Before the first Pixeltable operation, so the queries the agent runs show up under its tool calls in Logfire.
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()
PixeltableInstrumentor().instrument(span_level='debug')

TableModel.bind_all('market')

agent = Agent(
    f'google:{MODEL}',
    output_type=Picks,
    instructions=(
        'You help buyers on a secondhand marketplace. To search the listings, call similarity_search on photo_1 '
        "with words for what the buyer wants. Recommend only listings that fit the buyer's request, "
        'with their real id, title, and price. '
        'An empty list is a fine answer: say so in the note when nothing fits.'
    ),
    capabilities=[
        Pixeltable(['market.listings']),  # read-only search and queries over the listings
        Memory(PixeltableMemoryStore(table_name='market.memory')),  # the agent's notes, kept across runs
    ],
)


@agent.output_validator
def picks_are_listed(output: Picks) -> Picks:
    """Every pick must be a real listing at its real price."""
    ids = [pick.listing_id for pick in output.picks]
    rows = Listings.where(Listings.id.isin(ids)).select(Listings.id, Listings.price).collect()
    prices = {row['id']: row['price'] for row in rows}
    for pick in output.picks:
        if pick.listing_id not in prices:
            raise ModelRetry(f'{pick.listing_id} is not a listing id. Query the listing and use its id.')
        if prices[pick.listing_id] != pick.price:
            raise ModelRetry(f'Listing {pick.listing_id} costs {prices[pick.listing_id]}, not {pick.price}.')
    return output


if __name__ == '__main__':
    question = sys.argv[1] if len(sys.argv) > 1 else 'Something warm to read by in my living room, under $150?'
    result = agent.run_sync(question)
    print(result.output.model_dump_json(indent=2))
