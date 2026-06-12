"""CLI agent providers — no API keys; uses PATH + user auth."""

from books_agent.doctor import run_doctor
from books_agent.session import AgentPhase, prepare_session, run_agent

__all__ = ["run_doctor", "AgentPhase", "prepare_session", "run_agent"]
