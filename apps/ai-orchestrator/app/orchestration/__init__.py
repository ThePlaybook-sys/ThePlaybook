"""Async fan-out orchestration (Milestone 4.4). Runs the configured
Context & Data agents concurrently against one shared `AgentContext`,
isolating one agent's failure from the rest and reporting the
committee's overall participation state (FULL/PARTIAL/FAILED) --
Volume 4 Section 3.1's async fan-out flow, scoped here to the first
agent group only.
"""
