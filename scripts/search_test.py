"""Score the app's search on buyer searches whose right answer is written down: python scripts/search_test.py [base_url]

Each search has one listing that should come first. The catalog has near misses for every one:
listings of the same kind that differ on the point the buyer asked about.
"""

import sys

import httpx
from seed import LISTINGS

# (buyer's search, the listing that should come first, as its sample photo prefix)
SEARCHES = [
    # Lamps
    ('warm light for a reading nook', 'reading-floor-lamp'),
    ('bright white light for my garage workbench', 'work-light'),
    ('a soft dim glow for a bedside table', 'salt-lamp'),
    ('a hanging light for over my kitchen island', 'pendant-light'),
    ('a desk lamp with crisp daylight for detailed work', 'desk-lamp'),
    ('a classic desk lamp with warm light for a study', 'bankers-lamp'),
    ('a bold mid-century table lamp', 'table-lamp'),
    # Bags
    ('a backpack with a padded sleeve for my laptop', 'laptop-backpack'),
    ('a pack for a multi-day hike', 'hiking-pack'),
    ('a bag I can wear across my body on one shoulder', 'messenger-bag'),
    ('a bag for my gym clothes', 'duffel-bag'),
    ('a vintage leather backpack', 'backpack'),
    # Bikes
    ('a bike that folds up to take on the train', 'folding-bike'),
    ('something for rough mountain trails', 'mountain-bike'),
    ('a first bike for a 4-year-old', 'kids-bike'),
    ('a relaxed bike with a basket for errands around town', 'cruiser-bike'),
    ('a lightweight bike with drop bars for fast road rides', 'road-bike'),
]


def run(base_url: str) -> None:
    hits = 0
    seller_of = {slug: seller for slug, seller, _ in LISTINGS}
    with httpx.Client(base_url=base_url, timeout=60) as client:
        for query, expected in SEARCHES:
            rows = client.get('/search', params={'q': query, 'limit': 50}).raise_for_status().json()['rows']
            # Each sample listing has its own seller, so the seller identifies the listing.
            sellers = [client.get(f'/listings/{r["id"]}').raise_for_status().json()['seller'] for r in rows]
            rank = sellers.index(seller_of[expected]) + 1 if seller_of[expected] in sellers else None
            hits += rank == 1
            print(f'{"PASS" if rank == 1 else "FAIL"}  rank {rank}  {query!r}  -> first: {rows[0]["title"]}')
    print(f'\n{hits}/{len(SEARCHES)} searches put the right listing first')


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000')
