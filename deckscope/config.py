"""Run configuration: what model, what research backend, what lens, what output."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Lens(str, Enum):
    """The analytical posture the agents adopt."""

    INVESTOR = "investor"      # Is this worth funding? Diligence, risk, verdict.
    FOUNDER = "founder"        # How does my deck hold up? Gaps, weak claims, fixes.
    NEUTRAL = "neutral"        # Balanced deck-vs-market comparison, no recommendation.

    @classmethod
    def parse(cls, value: "str | Lens") -> "Lens":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            raise ValueError(
                f"Unknown lens {value!r}. Choose from: {', '.join(m.value for m in cls)}"
            ) from None


ALL_LENSES = [lens.value for lens in Lens]


@dataclass
class ProviderConfig:
    """Which model backend to talk to, and how."""

    name: str = "anthropic"            # anthropic | openai | openai_compatible | bedrock | mcp | manual | mock
    model: Optional[str] = None        # provider default used when None
    api_key_env: Optional[str] = None  # env var holding the key
    base_url: Optional[str] = None     # for self-hosted / proxy / Ollama / OpenRouter
    temperature: float = 0.2
    max_tokens: int = 8000
    timeout: int = 180
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchConfig:
    """Which web-research backend the MarketAnalyst uses."""

    name: str = "auto"                 # auto | tavily | serper | brave | mcp | provider_native | none
    max_results: int = 8
    max_queries: int = 8
    api_key_env: Optional[str] = None
    recency_days: Optional[int] = 540  # bias toward recent sources; None = no limit
    #: Run a second, deck-blind pass that researches the category cold.
    #:
    #: The main market pass is given the deck's claims — it has to be, it is
    #: checking them — which means its search is shaped by what the deck raises.
    #: That finds errors well and omissions badly. This pass sees only the
    #: category and a company name, so what it finds and the directed pass missed
    #: is a blind spot no prompt could have produced.
    cold_discovery: bool = False
    cold_max_queries: int = 6
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OpportunityConfig:
    """Whether to price the alternative, and on what assumptions.

    Off by default: it costs extra calls, and on a deck with no named public
    competitors it has nothing to say.
    """

    enabled: bool = False
    market_data: str = "auto"        # auto | search | none
    #: Assumptions for the required-outcome arithmetic. See opportunity.py.
    future_dilution: float = 0.50
    exit_revenue_multiple: float = 6.0
    horizon_years: int = 5
    preference_stack: float = 1.0


@dataclass
class OutputConfig:
    """What gets written, where."""

    formats: List[str] = field(default_factory=lambda: ["md"])
    out_dir: str = "./deckscope_output"
    basename: Optional[str] = None     # defaults to the deck's filename stem
    include_raw_json: bool = True
    theme: str = "slate"               # html/pptx/docx palette


@dataclass
class RunConfig:
    """Everything one analysis run needs."""

    deck_path: Optional[str] = None
    deck_text: Optional[str] = None
    company_hint: Optional[str] = None
    lenses: List[Lens] = field(default_factory=lambda: [Lens.INVESTOR])
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    # A cheaper/faster model may be used for extraction; falls back to `provider`.
    extract_provider: Optional[ProviderConfig] = None
    research: ResearchConfig = field(default_factory=ResearchConfig)
    opportunity: OpportunityConfig = field(default_factory=OpportunityConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    #: None means "the per-user application data directory", resolved at run time.
    #: It used to default to `.deckscope_cache` in the working directory, which put
    #: cleartext extractions of potentially confidential decks somewhere that gets
    #: committed, shared or cloud-synced by accident.
    cache_dir: Optional[str] = "__default__"
    verbose: bool = True
    #: Injection defenses. See deckscope/security/policy.py.
    security: Any = None  # SecurityPolicy; built in __post_init__

    def __post_init__(self) -> None:
        self.lenses = [Lens.parse(lens) for lens in self.lenses]
        if not self.lenses:
            self.lenses = [Lens.INVESTOR]
        if self.cache_dir == "__default__":
            from .settings import default_cache_dir
            self.cache_dir = str(default_cache_dir())

        from .security.policy import Mode, SecurityPolicy

        if self.security is None:
            self.security = SecurityPolicy()
        elif isinstance(self.security, str):
            self.security = SecurityPolicy(mode=Mode.parse(self.security))
        elif isinstance(self.security, dict):
            data = dict(self.security)
            if "mode" in data:
                data["mode"] = Mode.parse(data["mode"])
            self.security = SecurityPolicy(**data)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lenses"] = [lens.value for lens in self.lenses]
        sec = d.get("security") or {}
        if isinstance(sec, dict) and "mode" in sec:
            sec["mode"] = getattr(sec["mode"], "value", str(sec["mode"]))
        return d


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Optional[str] = None, **overrides: Any) -> RunConfig:
    """Load a RunConfig from YAML/JSON, env vars, and keyword overrides.

    Precedence: kwargs > file > env > defaults.
    """
    data: Dict[str, Any] = {}
    if path:
        import json
        raw = open(path, "r", encoding="utf-8").read()
        if path.endswith((".yaml", ".yml")):
            import yaml
            data = yaml.safe_load(raw) or {}
        else:
            data = json.loads(raw)

    env_provider = os.getenv("DECKSCOPE_PROVIDER")
    env_model = os.getenv("DECKSCOPE_MODEL")
    env_research = os.getenv("DECKSCOPE_RESEARCH")
    env_layer: Dict[str, Any] = {}
    if env_provider or env_model:
        env_layer["provider"] = {
            k: v for k, v in {"name": env_provider, "model": env_model}.items() if v
        }
    if env_research:
        env_layer["research"] = {"name": env_research}

    data = _merge(env_layer, data)
    data = _merge(data, overrides)

    provider = ProviderConfig(**data.pop("provider", {}) or {})
    xp = data.pop("extract_provider", None)
    extract_provider = ProviderConfig(**xp) if xp else None
    research = ResearchConfig(**data.pop("research", {}) or {})
    opportunity = OpportunityConfig(**data.pop("opportunity", {}) or {})
    output = OutputConfig(**data.pop("output", {}) or {})
    known = {f for f in RunConfig.__dataclass_fields__}
    data = {k: v for k, v in data.items() if k in known}

    return RunConfig(
        provider=provider,
        extract_provider=extract_provider,
        research=research,
        opportunity=opportunity,
        output=output,
        **data,
    )
