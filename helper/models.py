import os


GOOD_OPENROUTER_MODELS = (
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    "cohere/north-mini-code:free",
    "google/gemma-4-26b-a4b-it:free",
    "openai/gpt-oss-20b:free",
)

BAD_MODEL_MARKERS = ("content-safety", "safety")


def _configured_models() -> tuple[str, ...]:
    configured = os.getenv("AGENTSMITH_MODELS", "").strip()
    models = tuple(x.strip() for x in configured.split(",") if x.strip())
    return models or GOOD_OPENROUTER_MODELS


def is_usable_model(model: str) -> bool:
    lowered = model.lower()
    return model != "openrouter/free" and not any(
        marker in lowered for marker in BAD_MODEL_MARKERS
    )


def get_model_candidates(model_name: str | None = None) -> list[str]:
    """Return an ordered usable candidate list for routing.

    The first usable model is used as the primary model for the task.
    If it fails, the agent may fall back to later candidates.
    """
    candidates = [m for m in _configured_models() if is_usable_model(m)]
    if not candidates:
        raise ValueError("AGENTSMITH_MODELS contains no usable models")
    if model_name and is_usable_model(model_name):
        if model_name in candidates:
            candidates.remove(model_name)
        candidates.insert(0, model_name)
    return candidates


def pick_model(model_name: str | None = None) -> str:
    """Choose the primary usable model for this task."""
    return get_model_candidates(model_name)[0]


def model_pool_help() -> str:
    return ", ".join(get_model_candidates())
