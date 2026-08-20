"""Concrete inference providers.

Only the composition root imports this package (enforced by ``.importlinter``).
Every other layer depends on the ``ModelProvider`` protocol, which is what
makes the runtime replaceable.
"""

from cyberai.modules.inference.providers.mock import MockModelProvider
from cyberai.modules.inference.providers.openai_compatible import OpenAICompatibleModelProvider

__all__ = ["MockModelProvider", "OpenAICompatibleModelProvider"]
