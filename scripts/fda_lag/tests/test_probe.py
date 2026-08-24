"""Unit tests for the lag arithmetic. No network, no container — this is why `probe` is pure.

The tests worth having here are the ones where a wrong answer still looks like a distribution:
double-counting across overlapping windows, a null effective date silently read as zero, and an
ambiguous attribution reported as certain.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fda_lag.probe import (
    FinalRule,
    Observation,
    SectionVersion,
    announcement_lead_days,
    as_date,
    blind_spot_days,
    freshness_lag_days,
    load_observations,
    pair_candidates,
    summarize,
    unabsorbed_rules,
)


def _section(
    identifier: str = "820.35",
    *,
    part: str | None = "820",
    issue_date: str | None = "2026-02-04",
    removed: bool = False,
    substantive: bool = True,
) -> SectionVersion:
    return SectionVersion(
        identifier=identifier,
        part=part,
        subpart="B",
        issue_date=issue_date,
        amendment_date=issue_date,
        removed=removed,
        substantive=substantive,
    )


def _rule(
    document_number: str = "2024-01709",
    *,
    publication_date: str | None = "2024-02-02",
    effective_on: str | None = "2026-02-02",
    parts: tuple[str, ...] = ("820",),
) -> FinalRule:
    return FinalRule(
        document_number=document_number,
        citation="89 FR 7496",
        doc_type="Rule",
        publication_date=publication_date,
        effective_on=effective_on,
        parts=parts,
        title="Quality Management System Regulation",
    )


class TestDateParsing:
    def test_malformed_date_is_none_not_an_exception(self) -> None:
        # The run records what came back; one odd field must not kill a day's observation.
        assert as_date("not-a-date") is None
        assert as_date("") is None
        assert as_date(None) is None

    def test_iso_date_parses(self) -> None:
        assert as_date("2026-02-04") == date(2026, 2, 4)


class TestFreshnessLag:
    def test_measures_whole_days_behind(self) -> None:
        assert freshness_lag_days(date(2026, 8, 24), "2026-08-20") == 4

    def test_same_day_is_zero(self) -> None:
        assert freshness_lag_days(date(2026, 8, 20), "2026-08-20") == 0

    def test_absent_freshness_claim_is_none_not_zero(self) -> None:
        # A missing claim and a fresh title are opposite findings; conflating them would report
        # a broken endpoint as perfect freshness.
        assert freshness_lag_days(date(2026, 8, 24), None) is None
        assert freshness_lag_days(date(2026, 8, 24), "garbage") is None


class TestAnnouncementLead:
    def test_qmsr_pending_window(self) -> None:
        assert announcement_lead_days(_rule()) == 731

    def test_same_day_effective(self) -> None:
        rule = _rule(publication_date="2026-08-19", effective_on="2026-08-19")
        assert announcement_lead_days(rule) == 0

    def test_null_effective_date_is_none(self) -> None:
        assert announcement_lead_days(_rule(effective_on=None)) is None


class TestBlindSpot:
    """The distinction the first live run forced: *quiet* and *behind* are not the same number."""

    def test_a_quiet_compilation_is_not_a_blind_spot(self) -> None:
        # The case that produced freshness_lag_days=4 on 2026-08-24 with up_to_date_as_of
        # 2026-08-20. Nothing took effect in the gap, so the eCFR is current, not behind.
        rules = [_rule(publication_date="2026-08-19", effective_on="2026-08-19")]
        assert (
            blind_spot_days(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == 0
        )
        assert freshness_lag_days(date(2026, 8, 24), "2026-08-20") == 4

    def test_a_rule_in_force_and_absent_is_a_blind_spot(self) -> None:
        # Effective 08-21, but the title claims currency only to 08-20: the authority contradicts
        # itself, so the text cannot be present.
        rules = [_rule(publication_date="2026-08-21", effective_on="2026-08-21")]
        assert (
            blind_spot_days(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == 3
        )

    def test_a_future_effective_rule_is_not_a_blind_spot(self) -> None:
        # ADR-0018 decision 7: a pending amendment produces no version and is not a miss.
        rules = [_rule(publication_date="2026-08-05", effective_on="2027-01-15")]
        assert (
            unabsorbed_rules(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == ()
        )

    def test_a_rule_already_absorbed_is_not_a_blind_spot(self) -> None:
        rules = [_rule(publication_date="2026-08-01", effective_on="2026-08-10")]
        assert (
            unabsorbed_rules(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == ()
        )

    def test_the_oldest_unabsorbed_rule_sets_the_span(self) -> None:
        rules = [
            _rule("A", publication_date="2026-08-21", effective_on="2026-08-21"),
            _rule("B", publication_date="2026-08-23", effective_on="2026-08-23"),
        ]
        assert (
            blind_spot_days(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == 3
        )

    def test_null_effective_date_cannot_be_judged_absorbed_or_not(self) -> None:
        rules = [_rule(effective_on=None)]
        assert (
            unabsorbed_rules(rules, up_to_date_as_of="2026-08-20", observed_on=date(2026, 8, 24))
            == ()
        )

    def test_absent_freshness_claim_yields_no_blind_spot_measurement(self) -> None:
        rules = [_rule(publication_date="2026-08-21", effective_on="2026-08-21")]
        assert unabsorbed_rules(rules, up_to_date_as_of=None, observed_on=date(2026, 8, 24)) == ()


class TestPairing:
    def test_attributes_within_tolerance_and_measures_absorption(self) -> None:
        (pairing,) = pair_candidates([_section()], [_rule()])
        assert pairing.candidates == ("2024-01709",)
        assert pairing.absorption_lag_days == 2  # issued 02-04, effective 02-02
        assert pairing.basis == "effective_on"
        assert pairing.ambiguous is False

    def test_rule_for_a_different_part_is_not_a_candidate(self) -> None:
        (pairing,) = pair_candidates([_section()], [_rule(parts=("864",))])
        assert pairing.candidates == ()
        assert pairing.absorption_lag_days is None

    def test_outside_tolerance_is_not_a_candidate(self) -> None:
        (pairing,) = pair_candidates([_section()], [_rule()], tolerance_days=1)
        assert pairing.absorption_lag_days is None

    def test_falls_back_to_publication_date_and_says_so(self) -> None:
        rule = _rule(effective_on=None, publication_date="2026-02-04")
        (pairing,) = pair_candidates([_section()], [rule])
        assert pairing.basis == "publication_date"
        assert pairing.absorption_lag_days == 0

    def test_two_candidates_are_flagged_ambiguous_and_the_closest_wins(self) -> None:
        near = _rule("2024-23701", effective_on="2026-02-03")
        far = _rule("2024-01709", effective_on="2026-01-28")
        (pairing,) = pair_candidates([_section()], [far, near])
        assert pairing.ambiguous is True
        assert set(pairing.candidates) == {"2024-01709", "2024-23701"}
        assert pairing.absorption_lag_days == 1  # the nearer rule, not the first in the list

    def test_section_without_a_part_cannot_be_attributed(self) -> None:
        (pairing,) = pair_candidates([_section(part=None)], [_rule()])
        assert pairing.candidates == ()

    def test_in_scope_tagging_follows_the_part(self) -> None:
        in_scope, outside = pair_candidates(
            [_section(part="892"), _section("573.10", part="573")], [_rule()]
        )
        assert in_scope.in_scope is True
        assert outside.in_scope is False


class TestLoadObservations:
    def test_blank_lines_are_skipped(self) -> None:
        observations, errors = load_observations(['{"a": 1}', "", "   ", '{"b": 2}'])
        assert len(observations) == 2
        assert errors == []

    def test_a_truncated_line_is_reported_and_the_rest_survive(self) -> None:
        # A run killed mid-redirect must not discard a fortnight of good observations.
        observations, errors = load_observations(['{"a": 1}', '{"b": ', '{"c": 3}'])
        assert len(observations) == 2
        assert len(errors) == 1
        assert "line 2" in errors[0]

    def test_a_leading_bom_is_stripped_not_reported(self) -> None:
        # PowerShell's `>>` writes EF BB BF when it creates the file, so a log recreated on
        # Windows would otherwise lose its first observation silently.
        observations, errors = load_observations(['﻿{"observed_on": "2026-08-24"}'])
        assert errors == []
        assert observations == [{"observed_on": "2026-08-24"}]

    def test_a_non_object_line_is_an_error(self) -> None:
        observations, errors = load_observations(["[1, 2, 3]"])
        assert observations == []
        assert "expected an object" in errors[0]


def _observation(observed_on: str, pairings: list[dict[str, object]], **extra: object) -> dict:
    return {
        "observed_on": observed_on,
        "freshness_lag_days": extra.get("freshness", 1),
        "pairings": pairings,
        "final_rules": extra.get("final_rules", []),
        "truncated": extra.get("truncated", {}),
        "notes": extra.get("notes", []),
    }


def _pairing(section: str, issue_date: str, lag: int | None, **extra: object) -> dict:
    return {
        "section": section,
        "issue_date": issue_date,
        "absorption_lag_days": lag,
        "basis": extra.get("basis", "effective_on" if lag is not None else None),
        "in_scope": extra.get("in_scope", True),
        "removed": extra.get("removed", False),
        "substantive": True,
        "ambiguous": extra.get("ambiguous", False),
    }


class TestSummarize:
    def test_the_same_amendment_seen_on_many_days_counts_once(self) -> None:
        # The load-bearing property. Runs re-read an overlapping window by design, so counting
        # rows per observation would multiply one amendment by the lookback length — inflating
        # every count into something that still looks like a plausible distribution.
        pairings = [_pairing("892.5060", "2026-08-06", 0)]
        summary = summarize(
            [
                _observation("2026-08-24", pairings),
                _observation("2026-08-25", pairings),
                _observation("2026-08-26", pairings),
            ]
        )
        assert summary["distinct_section_versions"] == 1
        assert summary["absorption_lag_days"]["n"] == 1
        assert summary["days_observed"] == 3
        assert summary["observations"] == 3

    def test_a_later_run_attributing_what_an_earlier_one_could_not(self) -> None:
        # The rule can be published after the section was issued, so attribution can arrive late.
        summary = summarize(
            [
                _observation("2026-08-24", [_pairing("892.5060", "2026-08-06", None)]),
                _observation("2026-08-25", [_pairing("892.5060", "2026-08-06", 3)]),
            ]
        )
        assert summary["unattributed_section_versions"] == 0
        assert summary["absorption_lag_days"]["n"] == 1

    def test_freshness_distribution_spans_observations(self) -> None:
        summary = summarize(
            [
                _observation("2026-08-24", [], freshness=1),
                _observation("2026-08-25", [], freshness=5),
                _observation("2026-08-26", [], freshness=3),
            ]
        )
        assert summary["freshness_lag_days"] == {"n": 3, "min": 1, "median": 3, "max": 5}

    def test_absent_freshness_is_excluded_rather_than_counted_as_zero(self) -> None:
        summary = summarize(
            [
                _observation("2026-08-24", [], freshness=2),
                _observation("2026-08-25", [], freshness=None),
            ]
        )
        assert summary["freshness_lag_days"]["n"] == 1
        assert summary["freshness_lag_days"]["min"] == 2

    def test_rules_are_deduped_and_null_effective_dates_counted_separately(self) -> None:
        rules = [
            {
                "document_number": "2026-16942",
                "publication_date": "2026-08-19",
                "effective_on": "2026-08-19",
            },
            {
                "document_number": "2026-16420",
                "publication_date": "2026-08-12",
                "effective_on": None,
            },
        ]
        summary = summarize(
            [
                _observation("2026-08-24", [], final_rules=rules),
                _observation("2026-08-25", [], final_rules=rules),
            ]
        )
        assert summary["distinct_rules"] == 2
        assert summary["rules_without_effective_date"] == 1
        assert summary["announcement_lead_days"] == {"n": 1, "min": 0, "median": 0, "max": 0}

    def test_removed_and_in_scope_are_counted(self) -> None:
        summary = summarize(
            [
                _observation(
                    "2026-08-24",
                    [
                        _pairing("820.30", "2026-02-04", 2, removed=True),
                        _pairing("573.10", "2026-08-19", 0, in_scope=False),
                    ],
                )
            ]
        )
        assert summary["removed_section_versions"] == 1
        assert summary["in_scope_section_versions"] == 1
        assert summary["distinct_section_versions"] == 2

    def test_ambiguous_attributions_are_surfaced(self) -> None:
        summary = summarize(
            [_observation("2026-08-24", [_pairing("820.35", "2026-02-04", 1, ambiguous=True)])]
        )
        assert summary["ambiguous_attributions"] == 1

    def test_empty_log_summarizes_without_raising(self) -> None:
        summary = summarize([])
        assert summary["observations"] == 0
        assert summary["days_observed"] == 0
        assert summary["freshness_lag_days"] == {"n": 0}
        assert summary["first_day"] is None

    def test_truncation_and_notes_are_counted(self) -> None:
        summary = summarize(
            [
                _observation("2026-08-24", [], truncated={"federal_register": True}),
                _observation("2026-08-25", [], notes=["import_in_progress"]),
                _observation("2026-08-26", [], truncated={"federal_register": False}),
            ]
        )
        assert summary["truncated_observations"] == 1
        assert summary["observations_with_notes"] == 1


class TestObservationSerialization:
    def test_round_trips_through_jsonl(self) -> None:
        observation = Observation(
            observed_at="2026-08-24T06:00:00+00:00",
            observed_on="2026-08-24",
            lookback_from="2026-07-25",
            title=21,
            freshness_lag_days=4,
            blind_spot_days=0,
            unabsorbed_rules=[],
            title_state={"up_to_date_as_of": "2026-08-20"},
            in_scope_parts=["820"],
            section_versions=[],
            final_rules=[],
            pairings=[_pairing("820.35", "2026-02-04", 2)],
            truncated={"ecfr_versions": False, "federal_register": False},
        )
        line = observation.to_json()
        assert "\n" not in line  # one observation, one line — the log stays append-only
        reloaded, errors = load_observations([line])
        assert errors == []
        assert reloaded[0] == asdict(observation)
