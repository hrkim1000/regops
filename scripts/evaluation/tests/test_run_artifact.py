"""The run artifact, and the one place it can lie: a citation nobody looked up.

``resolves`` absent and ``resolves: false`` are different facts. The first means the resolution pass
has not run; the second means the cited clause does not exist at the version named, which is a
fabrication. Reading the first as the second is how the first full run — which died at the
resolution step after collecting every answer — reported a **100% hallucination rate** on five
citations nobody had checked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evaluation.run import RunArtifact, observations_from, unresolved_citations


def _artifact(resolves: bool | None) -> RunArtifact:
    citation = {"claim_index": 0, "document_version_id": "v1", "clause_path": "제1조"}
    if resolves is not None:
        citation["resolves"] = resolves
    return RunArtifact(
        run_id="r1",
        cell="mfds_cosmetic",
        started_at="2026-08-13T00:00:00+00:00",
        golden_set_version="1.0.0",
        ra_signed_off=False,
        observations={"a": {"status": "answered", "citations": [citation]}},
    )


def test_an_unchecked_citation_is_counted_as_unresolved_not_as_false():
    assert unresolved_citations(_artifact(None)) == 1
    assert unresolved_citations(_artifact(False)) == 0
    assert unresolved_citations(_artifact(True)) == 0


def test_scoring_an_artifact_with_unchecked_citations_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="never been checked"):
        observations_from(_artifact(None))


def test_a_checked_citation_reads_through_as_written():
    observed = observations_from(_artifact(True))
    assert observed["a"].citations[0].resolves is True
    assert observations_from(_artifact(False))["a"].citations[0].resolves is False


def test_an_errored_item_carries_no_citations_and_never_blocks_scoring():
    """A harness error has nothing to resolve, so it must not block scoring the whole artifact."""
    artifact = RunArtifact(
        run_id="r1",
        cell="mfds_samd",
        started_at="2026-08-13T00:00:00+00:00",
        golden_set_version="1.0.0",
        ra_signed_off=False,
        observations={"a": {"error": "timeout"}},
    )
    assert unresolved_citations(artifact) == 0
    assert observations_from(artifact)["a"].error == "timeout"


def test_the_artifact_round_trips_through_disk(tmp_path: Path):
    """The artifact, not the process, is the run — so a resumed run has to read back what a
    crashed one wrote."""
    original = _artifact(True)
    target = tmp_path / "run.json"
    original.save(target)

    restored = RunArtifact.load(target)
    assert restored is not None
    assert restored.run_id == original.run_id
    assert restored.observations == original.observations
    assert json.loads(target.read_text(encoding="utf-8"))["cell"] == "mfds_cosmetic"


def test_loading_a_run_that_does_not_exist_returns_none_rather_than_an_empty_run():
    """An empty run and no run are different: the first would resume by skipping nothing and
    silently start over, reporting a fresh run id for work already done."""
    assert RunArtifact.load(Path("does-not-exist.json")) is None
