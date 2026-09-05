"""The AI layer: provider-agnostic LLM orchestration over the tool boundary.

Switching between Claude and Sarvam is a config change (LLM_PROVIDER in
.env), never a code change — both speak the same neutral conversation
format and drive the identical `crew_ops.tools` boundary.
"""

from .config import ConfigError, load_env, provider_from_env
from .providers import ProviderError
from .agent import Advisor

__all__ = ["Advisor", "ConfigError", "ProviderError", "load_env",
           "provider_from_env"]
