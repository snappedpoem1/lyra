from __future__ import annotations

from oracle.agent import Agent, AgentEngine


def test_agent_engine_alias_points_to_agent_class():
    assert AgentEngine is Agent
