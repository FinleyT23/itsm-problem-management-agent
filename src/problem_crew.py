"""
problem_crew.py — FinServe Problem Management Crew Assembly
============================================================
Assembles the five-agent sequential crew following the ITIL 4
Problem Management lifecycle pipeline.
"""

from crewai import Crew, Process
from src.agents import create_agents
from src.tasks import task1, task2, task3, task4, task5


def create_problem_crew() -> Crew:
    """
    Creates the FinServe Problem Management crew.

    Task Pipeline (sequential):
    ─────────────────────────────────────────────────────────────────
    Task 1  Trend Analyst          Pattern Detection & Statistical Analysis
    Task 2  CMDB Correlator        CMDB Enrichment & Problem Records
    Task 3  Root Cause Investigator Five Whys Root Cause Analysis
    Task 4  Known Error Author      KEDB Documentation
    Task 5  Change Proposer         RFC Generation & Executive Summary
    ─────────────────────────────────────────────────────────────────

    Each task passes its full output as context to all downstream tasks
    via CrewAI's context chaining mechanism.
    """
    agents = create_agents()

    return Crew(
        agents=agents,
        tasks=[task1, task2, task3, task4, task5],
        process=Process.sequential,
        verbose=True,
        memory=False,    # No cross-run memory; each run is an independent investigation
        cache=True       # Cache tool calls to avoid redundant CSV reads during the run
    )
