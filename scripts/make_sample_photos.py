"""Generate the sample listing photos with OpenAI's image API.

These are generated product shots, so the demo has three consistent angles per item.
Swap in your own photos to try it on real listings.
"""

import base64
from pathlib import Path

from openai import OpenAI

ITEMS = {
    'film-camera': 'a used 1970s 35mm film SLR camera with a 50mm lens, silver and black, light wear on the edges',
    'road-bike': 'a used steel road bike, dark green frame, drop handlebars, leaning against a white wall',
    'table-lamp': 'a mid-century modern table lamp with a mushroom-shaped orange glass shade, walnut base',
    'backpack': 'a brown leather backpack with brass buckles, worn and soft, two front pockets',
    'guitar': 'a used acoustic guitar, natural spruce top, a small scratch near the soundhole',
}
ANGLES = [
    'Front view, centered, on a plain light background, natural daylight, a phone photo for a marketplace listing.',
    'The same item from the side or back, same background and light.',
    'A close-up of one detail of the same item that a buyer would want to see, same light.',
]

client = OpenAI()
out = Path(__file__).parent.parent / 'samples'
for slug, item in ITEMS.items():
    first = out / f'{slug}-1.png'
    if not first.exists():
        img = client.images.generate(model='gpt-image-1-mini', prompt=f'{item}. {ANGLES[0]}', size='1024x1024', quality='low')
        first.write_bytes(base64.b64decode(img.data[0].b64_json))
    for i, angle in enumerate(ANGLES[1:], start=2):
        path = out / f'{slug}-{i}.png'
        if path.exists():
            continue
        with first.open('rb') as f:
            img = client.images.edit(model='gpt-image-1-mini', image=f, prompt=f'{item}. {angle}', size='1024x1024', quality='low')
        path.write_bytes(base64.b64decode(img.data[0].b64_json))
    print(slug, 'done')
