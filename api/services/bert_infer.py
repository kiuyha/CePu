"""
Inference IndoBERT.
"""
import asyncio
from typing import Optional

from ..core.config import get_settings

_settings = get_settings()

_model = None
_tokenizer = None
_ner_pipeline = None
_inference_semaphore: Optional["asyncio.Semaphore"] = None
_load_error: Optional[str] = None


def is_model_loaded() -> bool:
    return _model is not None and _tokenizer is not None


def is_ner_loaded() -> bool:
    return _ner_pipeline is not None


def get_load_error() -> Optional[str]:
    return _load_error


def _mark_loaded_for_tests() -> None:
    global _model, _tokenizer, _ner_pipeline, _inference_semaphore
    _model = object()
    _tokenizer = object()
    _ner_pipeline = object()
    if _inference_semaphore is None:
        _inference_semaphore = asyncio.Semaphore(_settings.bert_max_concurrent_inference)


async def load_model() -> None:
    """Dipanggil sekali saat startup aplikasi. Gagal load TIDAK melempar exception ke atas."""
    global _model, _tokenizer, _ner_pipeline, _inference_semaphore, _load_error

    _inference_semaphore = asyncio.Semaphore(_settings.bert_max_concurrent_inference)

    def _blocking_load():
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(_settings.hf_model_id)
        model = AutoModelForSequenceClassification.from_pretrained(_settings.hf_model_id)
        model.eval()

        try:
            ner_pipe = pipeline(
                "ner",
                model=_settings.ner_model_id,
                tokenizer=_settings.ner_model_id,
                aggregation_strategy="simple",
                device=-1,  # CPU by default for stability
                stride=64,
            )
            ner_pipe.tokenizer.model_max_length = _settings.ner_max_length
        except Exception:
            ner_pipe = None

        return model, tokenizer, ner_pipe

    try:
        _model, _tokenizer, _ner_pipeline = await asyncio.to_thread(_blocking_load)
        _load_error = None
    except Exception as exc:  # noqa: BLE001
        _model = None
        _tokenizer = None
        _ner_pipeline = None
        _load_error = str(exc)


async def run_ner(text: str) -> list[dict]:
    """Menjalankan NER pipeline untuk mengekstraksi entitas dari teks."""
    if not is_ner_loaded() or not callable(_ner_pipeline):
        return []

    def _blocking_ner():
        return _ner_pipeline(text)

    return await asyncio.to_thread(_blocking_ner)


async def predict_fraud_probability(text: str) -> float:
    """Return P(fraud) -- probabilitas kelas fraud (index 1), bukan confidence label prediksi."""
    if not is_model_loaded():
        raise RuntimeError("Model belum dimuat. Panggil load_model() dulu, atau cek /healthz.")

    def _blocking_predict():
        import torch

        inputs = _tokenizer(
            text,
            truncation=True,
            max_length=_settings.bert_max_length,
            padding="max_length",
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = _model(**inputs).logits
        probs = torch.softmax(logits, dim=1).numpy()[0]
        return float(probs[1])

    async with _inference_semaphore:
        return await asyncio.to_thread(_blocking_predict)

