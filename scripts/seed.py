"""Post the sample listings to a running app: python scripts/seed.py [base_url]"""

import sys
from pathlib import Path

import httpx

SAMPLES = Path(__file__).parent.parent / 'samples'
LISTINGS = [
    ('film-camera', 'maya', 180),
    ('road-bike', 'sam', 420),
    ('table-lamp', 'ana', 95),
    ('backpack', 'lee', 140),
    ('guitar', 'kofi', 260),
]

base_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'
with httpx.Client(base_url=base_url, timeout=120) as client:
    for slug, seller, price in LISTINGS:
        files = {f'photo_{i}': (f'{slug}-{i}.jpg', (SAMPLES / f'{slug}-{i}.jpg').read_bytes(), 'image/jpeg') for i in (1, 2, 3)}
        resp = client.post('/listings', data={'seller': seller, 'price': price}, files=files)
        resp.raise_for_status()
        listing = resp.json()
        print(f"{listing['title']} ({listing['details']['condition']}): {listing['promo']}")
