"""Provider-neutral AI model layer (Milestone 4.3).

Architecture: Agent -> Model Router (`router.py`) -> `ModelAdapter`
(`base.py`) -> `OpenAIModelAdapter` / `AnthropicModelAdapter` /
`FakeModelAdapter`, orchestrated by `RetryEngine` (`retry_policy.py`) for
retry/fallback. Nothing outside this package knows or cares which
provider/model is actually in use -- see each module's own docstring for
its exact scope.

No agent exists yet (Milestone 4.4+). No live OpenAI/Anthropic call is
made or authorized anywhere in this package as of Milestone 4.3.
"""
