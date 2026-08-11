"""Requirement Extraction — the `regulation` service's agent (ADR-0004, ADR-0008).

Four modules, split along the deterministic/non-deterministic line ADR-0008 draws:

- :mod:`.rules` — the domain branch as *data*: modal inventory, taxonomy, prompt selection, and the
  deterministic triage that decides which clauses an LLM ever sees. No LLM.
- :mod:`.prompt` — the versioned prompt. No LLM.
- :mod:`.agent` — the only module that calls :func:`get_llm_client`. Everything it returns is
  validated back against the rule set before it can reach a row.
- :mod:`.extract` / :mod:`.staleness` — orchestration: classify every clause, write draft IRs with
  citations, and re-derive on amendment.
"""

from .agent import AgentResult, Proposal, extract_clause, parse_completion
from .extract import ExtractionResult, domains_for, extract_version
from .rules import RuleSet, Triage, found_modals, has_permissive, rule_set_for, triage
from .staleness import RederivationResult, mark_stale, rederive_version

__all__ = [
    "AgentResult",
    "ExtractionResult",
    "Proposal",
    "RederivationResult",
    "RuleSet",
    "Triage",
    "domains_for",
    "extract_clause",
    "extract_version",
    "found_modals",
    "has_permissive",
    "mark_stale",
    "parse_completion",
    "rederive_version",
    "rule_set_for",
    "triage",
]
