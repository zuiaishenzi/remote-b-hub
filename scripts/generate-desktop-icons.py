"""Draw original vector-style application marks and export multi-size Windows icons."""
from pathlib import Path
from PIL import Image, ImageDraw


def draw_mark(product, size=256):
    scale = 4
    side = size * scale
    image = Image.new('RGBA', (side, side))
    draw = ImageDraw.Draw(image)
    def box(values): return tuple(round(v * side / 256) for v in values)
    base = '#3859df' if product == 'a' else '#0d827e'
    draw.rounded_rectangle(box((5,5,251,251)), radius=round(side*.22), fill=base)
    draw.rounded_rectangle(box((17,17,239,239)), radius=round(side*.18), outline='#ffffff28', width=max(1,side//128))
    draw.polygon([box(p) for p in [(128,53),(194,91),(128,130),(62,91)]], fill='#ffffff')
    draw.polygon([box(p) for p in [(62,103),(121,138),(121,207),(62,171)]], fill='#c6d7ff' if product=='a' else '#b6f0df')
    draw.polygon([box(p) for p in [(135,138),(194,103),(194,171),(135,207)]], fill='#ffffff')
    # One detached connection node makes the cube recognizable at small sizes.
    draw.line([box((194,91)),box((216,77)),box((216,50))], fill='#8ee7d8' if product=='a' else '#a6caff', width=max(2,side//40))
    draw.ellipse(box((205,32,227,54)),fill='#b5f3df' if product=='a' else '#cfdeff')
    return image.resize((size,size),Image.Resampling.LANCZOS)


if __name__ == '__main__':
    folder=Path(__file__).resolve().parents[1]/'assets'
    folder.mkdir(exist_ok=True)
    for product,name in [('a','RemoteBClient'),('b','RemoteBHub')]:
        image=draw_mark(product)
        image.save(folder/(name+'.png'))
        image.save(folder/(name+'.ico'),sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
