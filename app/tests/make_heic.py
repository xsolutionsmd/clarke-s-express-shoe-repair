"""Fetch one pinned upstream iPhone benchmark only into the disposable test image.

Source: pillow-heif benchmark documentation identifies pug.heic as a 12MP iPhone
photo with metadata. No downloaded image is copied into the repository or runtime.
"""
import hashlib
from pathlib import Path
import urllib.request
from PIL import Image
import pillow_heif

url='https://raw.githubusercontent.com/bigcat88/pillow_heif/34d117af852041cc9564053c5ec613f3ea6b5fb5/tests/images/heif_other/pug.heic'
data=urllib.request.urlopen(url,timeout=30).read(10485760)
assert hashlib.sha256(data).hexdigest()=='1ddce96766efbfa0f6bdf634bdab26bdeff831393df8d67f4cdc7b7a7afebc67'
directory=Path('/opt/test-fixtures');directory.mkdir(exist_ok=True)
path=directory/'phone-12mp.heic';path.write_bytes(data)
pillow_heif.register_heif_opener()
with Image.open(path) as image:
    assert image.size==(4032,3024) and image.getexif()
