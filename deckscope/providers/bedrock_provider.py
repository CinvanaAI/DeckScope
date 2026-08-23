"""AWS Bedrock via boto3 (Anthropic, Llama, Mistral, Titan model IDs)."""
from __future__ import annotations

import json
from typing import Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError


class BedrockProvider(LLMProvider):
    name = "bedrock"
    default_model = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    catalog = [
        ("anthropic.claude-sonnet-4-5-20250929-v1:0", "Claude on Bedrock — recommended"),
        ("meta.llama3-3-70b-instruct-v1:0", "Llama 3.3 70B"),
    ]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        try:
            import boto3  # type: ignore
        except ImportError:
            raise ProviderError(
                "Bedrock needs boto3. Install it with: pip install boto3"
            ) from None
        region = self.config.extra.get("region") or "us-east-1"
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        # Bedrock's Converse API normalizes across model families.
        try:
            resp = self._client.converse(
                modelId=self.model,
                system=[{"text": system}],
                messages=[{"role": m.role, "content": [{"text": m.content}]}
                          for m in messages],
                inferenceConfig={
                    "maxTokens": max_tokens or self.config.max_tokens,
                    "temperature": (self.config.temperature
                                    if temperature is None else temperature),
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Bedrock call failed: {exc}") from None
        blocks = resp["output"]["message"]["content"]
        text = "".join(b.get("text", "") for b in blocks)
        u = resp.get("usage", {})
        return Completion(text=text, raw=resp, model=self.model,
                          usage={"input": u.get("inputTokens", 0),
                                 "output": u.get("outputTokens", 0)})
