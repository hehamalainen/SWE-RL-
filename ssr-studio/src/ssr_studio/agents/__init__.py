"""
SSR Studio Agents.

This module contains the bug injector and solver agents
that implement the SSR self-play pipeline.
"""

from ssr_studio.agents.injector import InjectorAgent
from ssr_studio.agents.solver import SolverAgent

__all__ = ["InjectorAgent", "SolverAgent"]
