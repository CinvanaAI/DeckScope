"""Provider/registry contracts — the parts other people will extend."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import Lens, ProviderConfig, RunConfig, load_config
from deckscope.providers.base import Completion, LLMProvider, extract_json, extract_json_array
from deckscope.providers.registry import get_provider, list_providers, register_provider
from deckscope.render.registry import list_formats, register_renderer, resolve
from deckscope.research.registry import list_researchers


def test_builtin_providers_registered():
    names = list_providers()
    assert {"anthropic", "openai", "mock", "manual", "mcp", "cli"} <= set(names)


def test_mock_provider_health():
    p = get_provider(ProviderConfig(name="mock"))
    assert p.health_check()["ok"] is True


def test_custom_provider_can_be_registered():
    class Toy(LLMProvider):
        name = "toy"
        default_model = "toy-1"

        def complete(self, system, messages, **kw):
            return Completion(text='{"ok": true}')

    register_provider(Toy)
    assert "toy" in list_providers()
    p = get_provider(ProviderConfig(name="toy"))
    assert p.complete_json("sys", "user") == {"ok": True}


def test_json_recovery_from_messy_output():
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"a": 1, }') == {"a": 1}          # trailing comma
    assert extract_json('prose {"a": "b"} more prose') == {"a": "b"}
    assert extract_json("no json here") is None
    assert extract_json_array('```\n["a","b"]\n```') == ["a", "b"]


def test_format_aliases():
    assert resolve("markdown") == "md"
    assert resolve("Word") == "docx"
    assert resolve(".PPTX") == "pptx"
    assert {"md", "html", "pdf", "docx", "pptx", "xlsx", "json", "txt"} <= set(list_formats())


def test_custom_renderer_can_be_registered():
    def toy(result, out_dir, base, **kw):
        p = out_dir / f"{base}.toy"
        p.write_text("hi", encoding="utf-8")
        return [str(p)]

    register_renderer("toy", toy, "A toy format")
    assert "toy" in list_formats()


def test_research_backends_registered():
    assert {"tavily", "serper", "brave", "exa", "none", "mcp",
            "provider_native"} <= set(list_researchers())


def test_lens_parsing():
    assert Lens.parse("investor") is Lens.INVESTOR
    assert Lens.parse(Lens.FOUNDER) is Lens.FOUNDER
    try:
        Lens.parse("banker")
    except ValueError as exc:
        assert "Unknown lens" in str(exc)
    else:
        raise AssertionError("should reject an unknown lens")


def test_config_defaults_and_security():
    cfg = RunConfig()
    assert cfg.lenses == [Lens.INVESTOR]
    assert cfg.security.mode.value == "balanced"
    cfg2 = load_config(None, security="strict", lenses=["founder", "neutral"])
    assert cfg2.security.mode.value == "strict"
    assert [x.value for x in cfg2.lenses] == ["founder", "neutral"]
    assert cfg2.to_dict()["security"]["mode"] == "strict"
