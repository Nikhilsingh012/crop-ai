from io import BytesIO

from PIL import Image

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def validate_image(upload):
    if upload.mimetype not in ALLOWED_TYPES:
        raise ValueError("Only JPG, PNG, or WEBP images are supported.")

    image_bytes = upload.read()
    if not image_bytes:
        raise ValueError("The uploaded image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be smaller than 10 MB.")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except Exception as error:
        raise ValueError("The uploaded file is not a valid image.") from error

    return image_bytes
