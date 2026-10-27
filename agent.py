"""The buyer's agent again, built with Pydantic AI: python agent.py "what are you looking for?"

app.py has its own buyer's agent (POST /ask), built from Pixeltable alone: the question is a row,
and Gemini calls the app's query through `pxt.tools`. This file shows the other way: an agent you
already run in Pydantic AI reads the same listings table through the Pixeltable capability for
Pydantic AI Harness, and returns the same `Picks` model.
"""

import sys

import logfire
from pydantic_ai import Agent, ModelRetry
from pydantic_ai_harness import Pixeltable

from app import Listings, Picks, TableModel

TableModel.bind_all('market')

logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()

agent = Agent(
    'google:gemini-3.8-flash',
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
    for pick in output.picks:
        rows = Listings.where(Listings.id == pick.listing_id).select(Listings.price).collect()
        if len(rows) == 0:
            raise ModelRetry(f'{pick.listing_id} is not a listing id. Query the listing and use its id.')
        if rows[0]['price'] != pick.price:
            raise ModelRetry(f"Listing {pick.listing_id} costs {rows[0]['price']}, not {pick.price}.")
    return output


if __name__ == '__main__':
    question = sys.argv[1] if len(sys.argv) > 1 else 'Something warm to read by in my living room, under $150?'
    result = agent.run_sync(question)
    print(result.output.model_dump_json(indent=2))
