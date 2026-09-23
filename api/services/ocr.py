"""
Layanan OCR berbasis RapidOCR dengan ONNX Runtime.
Berjalan cepat dan efisien pada CPU (cocok untuk VPS).
"""
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_engine = None


def get_ocr_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
            logger.info("RapidOCR ONNX engine initialized successfully.")
        except Exception as e:
            logger.warning("Failed to initialize RapidOCR engine: %s", e)
            _engine = None
    return _engine


def extract_text_from_image_bytes(image_bytes: bytes) -> tuple[str, float]:
    """
    Ekstrak teks dan rata-rata skor keyakinan (confidence) dari bytes gambar.
    Mengembalikan (teks_tergabung, rata_rata_skor).
    """
    if not image_bytes:
        return "", 0.0

    engine = get_ocr_engine()
    if engine is None:
        return "", 0.0

    try:
        # RapidOCR menerima bytes gambar secara langsung atau ndarray
        results, elapse_list = engine(image_bytes)
        if not results:
            return "", 0.0

        texts = []
        scores = []
        for box, text, score in results:
            if text and text.strip():
                texts.append(text.strip())
                scores.append(float(score))

        combined_text = "\n".join(texts)
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return combined_text, avg_score
    except Exception as exc:
        logger.error("Error during OCR extraction: %s", exc)
        return "", 0.0
