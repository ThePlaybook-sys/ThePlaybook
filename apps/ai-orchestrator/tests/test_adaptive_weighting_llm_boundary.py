"""Milestone 5.5, Decision 20 -- no LLM (Large Language Model) or model
adapter of any kind participates in ROI, sample counting, confidence
calibration arithmetic, performance_delta, guardrail enforcement, or the
proposed-weight calculation. Proven by source inspection: neither the
deterministic engine nor its orchestration imports any model-call
machinery at all -- there is no adapter to accidentally invoke."""
from __future__ import annotations

import inspect

import app.features.adaptive_weighting as engine
import app.orchestration.adaptive_weighting as orchestration

_FORBIDDEN_REFERENCES = ("RetryEngine", "AdapterRegistry", "ModelRequest", "ModelRouter", "FakeModelAdapter", "AnthropicModelAdapter", "OpenAIModelAdapter")


def test_deterministic_engine_has_no_model_adapter_reference():
    source = inspect.getsource(engine)
    for forbidden in _FORBIDDEN_REFERENCES:
        assert forbidden not in source, f"{forbidden} must never appear in the deterministic weighting engine"


def test_orchestration_has_no_model_adapter_reference():
    source = inspect.getsource(orchestration)
    for forbidden in _FORBIDDEN_REFERENCES:
        assert forbidden not in source, f"{forbidden} must never appear in Milestone 5.5's orchestration"
