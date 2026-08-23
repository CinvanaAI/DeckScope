"""DeckScope - a provider-agnostic agentic framework for pitch deck + market analysis.

Three agents run in sequence:
    1. DeckAnalyst      -> extracts structured claims from a pitch deck
    2. MarketAnalyst    -> researches the market those claims live in
    3. ComparisonSynth  -> scores deck claims against market reality

Every layer is swappable: the model provider, the research backend,
the analytical lens, and the output format.
"""

#: Deliberately not a release number. DeckScope has not had a release: it has an
#: architecture that works and a list of things that are not yet proven. Calling
#: it 1.0 would claim a maturity the test suite does not yet back.
__version__ = "0.0.0.dev0"

from .config import RunConfig, Lens, load_config
from .orchestrator import Pipeline, analyze
from .providers.registry import get_provider, list_providers, register_provider
from .research.registry import get_researcher, list_researchers, register_researcher
from .render.registry import render, list_formats, register_renderer

__all__ = [
    "RunConfig", "Lens", "load_config",
    "Pipeline", "analyze",
    "get_provider", "list_providers", "register_provider",
    "get_researcher", "list_researchers", "register_researcher",
    "render", "list_formats", "register_renderer",
]
