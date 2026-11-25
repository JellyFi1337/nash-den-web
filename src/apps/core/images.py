"""Уменьшение загруженных фотографий."""

from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile
from PIL import Image, UnidentifiedImageError

MAX_SIDE = 640
# Pillow по умолчанию пускает около 179 млн пикселей. Меньший предел
# обрывает распаковку до того, как файл займёт память процесса.
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def shrink_image(field: FieldFile | None, max_side: int = MAX_SIDE) -> None:
    """Ужимает изображение до max_side по большей стороне и сохраняет как JPEG.

    Уже подходящий JPEG не перекодируется: повторное сохранение модели не портит файл.
    Чужой формат и слишком большое полотно не открываются: файл остаётся как был.
    """
    if not field:
        return
    try:
        field.open("rb")
        image = Image.open(field.file, formats=ALLOWED_FORMATS)
        image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
        return
    if image.format == "JPEG" and max(image.size) <= max_side:
        return
    rgb = image.convert("RGB")
    rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=85, optimize=True)
    stem = Path(field.name).stem or "image"
    field.save(f"{stem}.jpg", ContentFile(buffer.getvalue()), save=False)
