import cv2


def postprocess(image, settings):
    """Opt-in denoise and resize. Both are off by default to keep the film look."""
    if settings.denoise:
        image = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 29)
    if settings.resize_to:
        w, h = settings.resize_to
        upscaling = w * h > image.shape[1] * image.shape[0]
        image = cv2.resize(image, (w, h), interpolation=cv2.INTER_CUBIC if upscaling else cv2.INTER_AREA)
    return image
