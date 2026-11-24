"""The webinar's steps 1 to 6 in one file you can run: the code on the slides, on one small demo table.

Run it from the repo root, with GEMINI_API_KEY set:

    uv run python webinar/steps.py

It creates the folder `demo` with one table, `demo/listings`, next to the app's own tables. Step 4's
computed column calls Gemini on each photo you insert, so a run makes about three Gemini calls.
To run it again, drop the demo folder first:

    pxt drop-dir -r -f demo

The rest of the talk is in the app: the staging code from "When your LLM generates media" is in app.py,
step 7's agent is in agent.py, and step 8's Logfire setup is README.md's step 11.

The slides name the photos without their folder ('desk-lamp-1.jpg'); here they're under samples/.
Checked on Pixeltable 0.7.25.
"""

from pathlib import Path
from typing import Literal

import pixeltable as pxt
import pixeltable.functions as pxtf
from pydantic import BaseModel, Field

MODEL = 'gemini-3.8-flash'
DETAILS_PROMPT = 'Write a marketplace listing for the item in these photos. Describe only what the photos show.'


# Step 1. Define a Pydantic model for the data you insert
class PySellerNotes(BaseModel):
    brand: str
    year_bought: int
    has_original_box: bool


# Step 3. Define a Pydantic model for your LLM's output (app.py's ListingDetails)
class PyListingDetails(BaseModel):
    title: str = Field(description='A listing title, under 60 characters')
    category: Literal['cameras', 'bikes', 'home', 'bags', 'instruments', 'other']
    condition: Literal['new', 'like new', 'good', 'fair']
    color: str
    description: str = Field(description='Two or three sentences for buyers, about only what the photos show')
    pitch: str = Field(description='Narration for a 10-second listing video: two short spoken sentences, 15 to 25 words')


# Step 6. Convert query results back to your Pydantic model
class PyListingRow(BaseModel):
    notes: PySellerNotes
    details: PyListingDetails


# Step 2. Add that model to your Pixeltable schema as a JSON column
# Step 4. Use that model in a computed column that calls your LLM
TableModel = pxt.model_base()


class ListingsTable(TableModel, name='listings'):
    photo: pxt.Image                # step 2
    notes: pxt.Json[PySellerNotes]  # step 2
    response = pxtf.gemini.generate_content(  # step 4
        [DETAILS_PROMPT, photo],
        model=MODEL,
        config={'response_mime_type': 'application/json',
                'response_json_schema': PyListingDetails.model_json_schema()},
    )
    details = response.parsed.astype(pxt.Json[PyListingDetails])  # step 4


def show(label, call):
    """Run one call and print what it returned, or the first line of the error it raised."""
    try:
        result = call()
        print(f'{label}:', result if result is not None else 'ok')
    except Exception as e:
        print(f'{label}: {type(e).__name__}: {str(e).splitlines()[0]}')


if __name__ == '__main__':
    TableModel.create_all('demo')

    print('--- step 2: the notes are checked when the row comes in')
    good = {'brand': 'Lumina', 'year_bought': 2021, 'has_original_box': False}
    show('insert', lambda: ListingsTable.insert([{'photo': 'samples/desk-lamp-1.jpg', 'notes': good}]))
    show('insert, wrong type', lambda: ListingsTable.insert(
        [{'photo': 'samples/desk-lamp-1.jpg', 'notes': {**good, 'year_bought': 'last year'}}]))
    # RequestError: Error in column notes: expected int, got str

    print("--- step 4: Gemini's answer, checked against PyListingDetails")
    print(ListingsTable.select(ListingsTable.details).collect()[0]['details'])

    print("--- step 5: what an insert does with a value that doesn't fit")
    Path('not-a-photo.jpg').write_text('this is text, not a photo\n')
    rows = [{'photo': 'samples/desk-lamp-2.jpg', 'notes': good}, {'photo': 'not-a-photo.jpg', 'notes': good}]
    show('insert, the default: all or nothing', lambda: ListingsTable.insert(rows))
    # RequestError: Not a valid image: …/not-a-photo.jpg
    show("insert, on_error='ignore'", lambda: ListingsTable.insert(rows, on_error='ignore'))
    print(ListingsTable.where(ListingsTable.photo.errortype != None)
          .select(ListingsTable.photo.errortype, ListingsTable.photo.errormsg).collect())
    # When LLM calls fail, rerun the call (response), not the check (details), for just those rows.
    # Here the failed row's photo is broken, so rerunning the call leaves it failed.
    failed = ListingsTable.details.errortype != None
    ListingsTable.recompute_columns(ListingsTable.response, where=failed)

    print('--- step 6: query results back as your Pydantic model')
    rows = (ListingsTable.where(ListingsTable.details.errortype == None)
            .select(ListingsTable.notes, ListingsTable.details).collect())
    print(list(rows.to_pydantic(PyListingRow))[0])
