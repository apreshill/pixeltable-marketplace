"""Post the sample listings to a running app: python scripts/seed.py [base_url] [slug ...]"""

import sys
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).parent.parent / 'samples'
# (sample photo prefix, seller, price). Each seller has one listing.
LISTINGS = [
    ('film-camera', 'maya', 180),
    ('road-bike', 'sam', 420),
    ('table-lamp', 'ana', 95),
    ('backpack', 'lee', 140),
    ('guitar', 'kofi', 260),
    # Near misses: listings of the same kind that differ on what a buyer searches for.
    ('reading-floor-lamp', 'ines', 120),
    ('desk-lamp', 'raj', 45),
    ('pendant-light', 'tom', 70),
    ('work-light', 'dev', 30),
    ('salt-lamp', 'mei', 25),
    ('bankers-lamp', 'omar', 65),
    ('laptop-backpack', 'zoe', 55),
    ('hiking-pack', 'finn', 150),
    ('messenger-bag', 'ravi', 60),
    ('duffel-bag', 'ama', 35),
    ('mountain-bike', 'jon', 650),
    ('kids-bike', 'lia', 40),
    ('cruiser-bike', 'eva', 180),
    ('folding-bike', 'ken', 300),
]


def wait_for(client: httpx.Client, job_url: str) -> dict:
    """Poll a background job until it finishes, and return its result."""
    while True:
        job = client.get(job_url).raise_for_status().json()
        if job['status'] == 'done':
            return job['result']
        if job['status'] == 'error':
            raise RuntimeError(job['error'])
        time.sleep(1)


def seed(base_url: str, only: set[str] | None = None) -> None:
    with httpx.Client(base_url=base_url, timeout=180) as client:
        # Submit every listing, then wait for each listing's job.
        jobs = {}
        for slug, seller, price in LISTINGS:
            if only and slug not in only:
                continue
            files = {
                f'photo_{i}': (f'{slug}-{i}.jpg', (SAMPLES / f'{slug}-{i}.jpg').read_bytes(), 'image/jpeg')
                for i in (1, 2, 3)
            }
            resp = client.post('/listings', data={'seller': seller, 'price': price}, files=files)
            jobs[slug] = resp.raise_for_status().json()['job_url']
        failed = []
        for slug, job_url in jobs.items():
            try:
                listing = wait_for(client, job_url)
            except RuntimeError as e:
                # e.g. Gemini answers 503 when a model is overloaded; the rest of the listings still go in
                print(f'{slug}: FAILED: {str(e)[:200]}')
                failed.append(slug)
                continue
            print(f"{slug}: {listing['title']} | {listing['details']['description']}")
        if failed:
            print(f"\n{len(failed)} listing(s) failed. To retry just those: python scripts/seed.py {base_url} {' '.join(failed)}")


if __name__ == '__main__':
    seed(sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000', set(sys.argv[2:]) or None)
