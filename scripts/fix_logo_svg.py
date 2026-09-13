from pathlib import Path
import base64
import struct

png_path = Path(__file__).resolve().parent.parent / 'static' / 'logo.png'
svg_path = png_path.parent / 'logo.svg'

png = png_path.read_bytes()
if not png.startswith(b'\x89PNG\r\n\x1a\n'):
    raise ValueError('logo.png is not a valid PNG file')

width, height = struct.unpack('>II', png[16:24])
encoded = base64.b64encode(png).decode('ascii')
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">'
    f'<image width="{width}" height="{height}" href="data:image/png;base64,{encoded}" />'
    f'</svg>'
)
svg_path.write_text(svg, encoding='utf-8')
print(f'logo.svg rebuilt to {width}x{height}')
