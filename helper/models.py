import random


GOOD_OPENROUTER_MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
)


def pick_model(model_name: str | None = None) -> str:
    """Return an explicit model or choose one from the curated good pool."""
    if model_name:
        return model_name
    return random.SystemRandom().choice(GOOD_OPENROUTER_MODELS)


def model_pool_help() -> str:
    return ", ".join(GOOD_OPENROUTER_MODELS)
