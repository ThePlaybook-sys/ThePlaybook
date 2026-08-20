"""Demo Mode production code (DEMO-2, docs/blueprint/demo-simulation-environment.md).

Everything under this package exists to supply the *same* provider-neutral
adapter interfaces (`app/adapters/base.py`) with deterministic, obviously-
synthetic data instead of a real vendor's HTTP response -- never a second
implementation of Playbook business logic, per Rule 1 of the approved Demo
design. Nothing here is wired into any worker, cache, or persistence call
site yet; that begins at DEMO-3.
"""
