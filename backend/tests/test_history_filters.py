"""Regression tests: history filters must be applied in SQL before pagination.

Guards the Phase 9 fix where the status filter used to run after LIMIT/OFFSET,
reporting page-scoped totals and silently hiding matching inspections that
lived on other pages. Data is seeded directly through the ORM so a test can
create more than one page of matching rows quickly; assertions run against the
real HTTP endpoint and therefore the real query path.

Filter semantics (unchanged from Phase 9): filters compare the requested
states against each inspection's AUTOMATED rollup OR its OFFICER-EFFECTIVE
rollup (both derived per the evaluation services), and they operate on the
four inspection-level assessment states — COMPLIANT, NON_COMPLIANT,
REVIEW_REQUIRED, INCOMPLETE — never on raw per-rule statuses.
"""
import pytest

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.inspection import (
    ExtractedField,
    Inspection,
    InspectionEvaluation,
    OfficerDecision,
    OfficerVerification,
    RuleEvaluation,
)


def _seed(session, idx, statuses, decision=None, product=None, days_ago=0):
    """One inspection with a single evaluation of the given rule statuses.

    `statuses` are per-rule automated statuses; `decision` (optional) attaches
    one officer verification to the LAST rule of the evaluation.
    """
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    inspection = Inspection(
        inspection_id=f"LGA-2026-{90000 + idx:05d}", created_at=created, updated_at=created
    )
    session.add(inspection)
    session.flush()
    if product:
        session.add(
            ExtractedField(
                inspection_id=inspection.id,
                field_name="product_name",
                status="detected",
                value_json={"name": product},
                method="deterministic",
            )
        )
    evaluation = InspectionEvaluation(
        inspection_id=inspection.id,
        evaluation_version=1,
        engine_version="0.1.0",
        overall_status="TEST",
        created_at=created,
    )
    session.add(evaluation)
    session.flush()
    rules = []
    for i, status in enumerate(statuses):
        rule = RuleEvaluation(
            inspection_evaluation_id=evaluation.id,
            rule_id=f"LMPC-T{i}",
            rule_number=f"{i}",
            rule_title=f"t{i}",
            status=status,
            severity="mandatory",
            finding="f",
        )
        rules.append(rule)
        session.add(rule)
    session.flush()
    if decision is not None:
        session.add(
            OfficerVerification(
                inspection_id=inspection.id,
                inspection_evaluation_id=evaluation.id,
                rule_evaluation_id=rules[-1].id,
                officer_identifier="officer-test",
                decision=decision,
                comment="seed",
            )
        )
    session.flush()
    return inspection


def _listing(client, **params):
    response = client.get("/api/v1/inspections", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def seeded_db(monkeypatch):
    """Fresh SQLite DB exposed through the app's own session factory, so tests
    can seed rows with the ORM and the app reads the same data."""
    import os

    import sqlalchemy as sa
    import app.api.inspections as inspections_api
    import app.database as database
    from app.database import Base

    engine = sa.create_engine(
        "sqlite:///./.test-history-filters.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestingSession = sa.orm.sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr(inspections_api, "get_db", database.get_db)
    yield TestingSession
    from sqlalchemy.orm import close_all_sessions

    close_all_sessions()  # release checked-out SQLite handles (Windows locks)
    engine.dispose()
    os.remove(".test-history-filters.db")


class TestStatusFilterAcrossPages:
    def test_totals_and_pages_cover_full_filtered_set(self, client, seeded_db):
        """12 REVIEW_REQUIRED + 3 COMPLIANT inspections, page_size 5.

        The old post-query filter returned total=5, pages=1 and hid 7 rows.
        """
        session = seeded_db()
        # REVIEW_REQUIRED: 8 plain + 2 confirmed + 2 overridden-to-compliant.
        for i in range(8):
            _seed(session, i, ["REVIEW_REQUIRED", "COMPLIANT"])
        for i in range(8, 10):
            _seed(session, i, ["REVIEW_REQUIRED"], decision=OfficerDecision.CONFIRM_REVIEW_REQUIRED)
        for i in range(10, 12):
            _seed(session, i, ["REVIEW_REQUIRED"], decision=OfficerDecision.OVERRIDE_COMPLIANT)
        # COMPLIANT rows (automated): pure + overridden-to-violation.
        for i in range(12, 15):
            _seed(session, i, ["COMPLIANT"])
        _seed(session, 15, ["COMPLIANT"], decision=OfficerDecision.OVERRIDE_VIOLATION)
        session.commit()

        review = _listing(client, status="REVIEW_REQUIRED", page_size=5)
        # Semantics (unchanged): a row matches when automated OR effective
        # status is in the set. 8 automated REVIEW_REQUIRED + 2 confirmed;
        # the 2 overrides also match via their AUTOMATED status (12 total).
        assert review["total"] == 12
        assert review["pages"] == 3
        collected = []
        for page in (1, 2, 3):
            body = _listing(client, status="REVIEW_REQUIRED", page=page, page_size=5)
            assert body["page"] == page
            collected.extend(item["inspection_id"] for item in body["items"])
        assert len(collected) == 5 + 5 + 2, "every page filled except the last"
        assert len(set(collected)) == 12, "no duplicates across pages"
        assert len(collected) == review["total"], "no rows missed across pages"

        compliant = _listing(client, status="COMPLIANT", page_size=100)
        # 3 automated-COMPLIANT + 2 overrides-to-COMPLIANT effective; the
        # override-to-VIOLATION row also matches via its AUTOMATED status (6).
        assert compliant["total"] == 6

        violation = _listing(client, status="NON_COMPLIANT", page_size=100)
        assert violation["total"] == 1

    def test_comma_separated_multi_status(self, client, seeded_db):
        """Filters compare against the inspection-level rollup state, so a
        NOT_VERIFIABLE *rule* surfaces as the inspection's INCOMPLETE."""
        session = seeded_db()
        _seed(session, 0, ["COMPLIANT"])
        _seed(session, 1, ["REVIEW_REQUIRED"])
        _seed(session, 2, ["COMPLIANT", "NOT_VERIFIABLE"])
        session.commit()
        body = _listing(client, status="COMPLIANT,INCOMPLETE", page_size=100)
        ids = {i["inspection_id"] for i in body["items"]}
        assert body["total"] == 2
        assert ids == {"LGA-2026-90000", "LGA-2026-90002"}
        # A raw rule-level status value matches nothing: the filter operates
        # on the four inspection-level assessment states.
        assert _listing(client, status="NOT_VERIFIABLE", page_size=100)["total"] == 0

    def test_no_status_filter_unchanged(self, client, seeded_db):
        session = seeded_db()
        for i in range(7):
            _seed(session, i, ["COMPLIANT"])
        session.commit()
        body = _listing(client, page_size=3)
        assert body["total"] == 7
        assert body["pages"] == 3
        assert len(body["items"]) == 3
        page3 = _listing(client, page=3, page_size=3)
        assert len(page3["items"]) == 1


class TestStatusFilterEdgeCases:
    def test_no_matching_status_returns_empty_with_zero_totals(self, client, seeded_db):
        session = seeded_db()
        _seed(session, 0, ["COMPLIANT"])
        session.commit()
        body = _listing(client, status="NON_COMPLIANT")
        assert body["items"] == []
        assert body["total"] == 0 and body["pages"] == 0

    def test_beyond_last_page_is_empty_not_error(self, client, seeded_db):
        session = seeded_db()
        for i in range(3):
            _seed(session, i, ["COMPLIANT"])
        session.commit()
        body = _listing(client, status="COMPLIANT", page=99, page_size=2)
        assert body["items"] == []
        assert body["total"] == 3 and body["pages"] == 2 and body["page"] == 99

    def test_whitespace_and_case_tolerant(self, client, seeded_db):
        session = seeded_db()
        _seed(session, 0, ["COMPLIANT"])
        session.commit()
        body = _listing(client, status="  compliant , REVIEW_REQUIRED  ")
        assert body["total"] == 1

    def test_unknown_status_matches_nothing(self, client, seeded_db):
        session = seeded_db()
        _seed(session, 0, ["COMPLIANT"])
        session.commit()
        body = _listing(client, status="SOMETHING_ELSE")
        assert body["total"] == 0

    def test_inspection_without_evaluation_never_matches_status(self, client, seeded_db):
        session = seeded_db()
        bare = Inspection(inspection_id="LGA-2026-99999")
        session.add(bare)
        _seed(session, 0, ["COMPLIANT"])
        session.commit()
        body = _listing(client, status="COMPLIANT", page_size=100)
        assert "LGA-2026-99999" not in {i["inspection_id"] for i in body["items"]}
        # Unfiltered listing still shows it, honestly statusless.
        all_rows = _listing(client, page_size=100)
        bare_row = next(i for i in all_rows["items"] if i["inspection_id"] == "LGA-2026-99999")
        assert bare_row["automated_status"] is None and bare_row["has_evaluation"] is False

    def test_only_latest_evaluation_counts(self, client, seeded_db):
        session = seeded_db()
        inspection = _seed(session, 0, ["COMPLIANT"])
        v2 = InspectionEvaluation(
            inspection_id=inspection.id,
            evaluation_version=2,
            engine_version="0.1.0",
            overall_status="TEST2",
        )
        session.add(v2)
        session.flush()
        session.add(
            RuleEvaluation(
                inspection_evaluation_id=v2.id,
                rule_id="LMPC-X",
                rule_number="1",
                rule_title="x",
                status="REVIEW_REQUIRED",
                severity="mandatory",
                finding="f",
            )
        )
        session.commit()
        # v1 COMPLIANT, v2 REVIEW_REQUIRED → only REVIEW_REQUIRED matches.
        assert _listing(client, status="COMPLIANT", page_size=100)["total"] == 0
        assert _listing(client, status="REVIEW_REQUIRED", page_size=100)["total"] == 1
        row = _listing(client, page_size=100)["items"][0]
        assert row["evaluation_version"] == 2 and row["automated_status"] == "REVIEW_REQUIRED"

    def test_overrides_do_not_leak_across_inspections(self, client, seeded_db):
        session = seeded_db()
        _seed(session, 0, ["REVIEW_REQUIRED"], decision=OfficerDecision.OVERRIDE_VIOLATION)
        _seed(session, 1, ["REVIEW_REQUIRED"])
        session.commit()
        rows = {i["inspection_id"]: i for i in _listing(client, page_size=100)["items"]}
        assert rows["LGA-2026-90000"]["effective_status"] == "NON_COMPLIANT"
        assert rows["LGA-2026-90001"]["effective_status"] == "REVIEW_REQUIRED"

    def test_older_verification_loses_to_latest(self, client, seeded_db):
        """Two verifications on the same rule: the newest id wins (COMPLIANT)."""
        session = seeded_db()
        inspection = _seed(session, 0, ["REVIEW_REQUIRED"])
        evaluation = (
            session.query(InspectionEvaluation).filter_by(inspection_id=inspection.id).one()
        )
        rule = session.query(RuleEvaluation).filter_by(inspection_evaluation_id=evaluation.id).one()
        session.add(
            OfficerVerification(
                inspection_id=inspection.id,
                inspection_evaluation_id=evaluation.id,
                rule_evaluation_id=rule.id,
                officer_identifier="officer-a",
                decision=OfficerDecision.CONFIRM_REVIEW_REQUIRED,
                comment="first",
            )
        )
        session.flush()
        session.add(
            OfficerVerification(
                inspection_id=inspection.id,
                inspection_evaluation_id=evaluation.id,
                rule_evaluation_id=rule.id,
                officer_identifier="officer-b",
                decision=OfficerDecision.OVERRIDE_COMPLIANT,
                comment="second",
            )
        )
        session.commit()
        rows = {i["inspection_id"]: i for i in _listing(client, page_size=100)["items"]}
        assert rows["LGA-2026-90000"]["effective_status"] == "COMPLIANT"

    def test_search_and_status_compose(self, client, seeded_db):
        session = seeded_db()
        for i in range(4):
            _seed(session, i, ["COMPLIANT"], product=f"Widget {i}")
        session.commit()
        body = _listing(client, search="Widget 1", status="COMPLIANT", page_size=100)
        assert body["total"] == 1
        assert body["items"][0]["product_name"] == "Widget 1"

    def test_date_and_status_compose(self, client, seeded_db):
        session = seeded_db()
        _seed(session, 0, ["COMPLIANT"], days_ago=30)
        _seed(session, 1, ["COMPLIANT"], days_ago=0)
        session.commit()
        body = _listing(client, date_from="2099-01-01T00:00:00Z", status="COMPLIANT")
        assert body["total"] == 0
        recent = _listing(
            client,
            date_from=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            status="COMPLIANT",
            page_size=100,
        )
        assert {i["inspection_id"] for i in recent["items"]} == {"LGA-2026-90001"}


class TestAcceptBoundary:
    def test_accept_keeps_effective_but_marks_verified(self, client, seeded_db):
        """ACCEPT sets verification_required without changing the effective
        status — this flows through verification_service (ORM), while the SQL
        rollup drives the status column; the two paths must agree."""
        session = seeded_db()
        _seed(session, 0, ["REVIEW_REQUIRED", "COMPLIANT"], decision=OfficerDecision.ACCEPT)
        session.commit()
        rows = {i["inspection_id"]: i for i in _listing(client, page_size=100)["items"]}
        row = rows["LGA-2026-90000"]
        assert row["verification_required"] is True
        assert row["effective_status"] == row["automated_status"] == "REVIEW_REQUIRED"

        # Same result via the enriched evaluation payload (ORM path).
        from app.services import verification_service
        from app.services.evaluation_service import evaluation_out

        inspection = session.query(Inspection).filter_by(inspection_id="LGA-2026-90000").one()
        evaluation = (
            session.query(InspectionEvaluation).filter_by(inspection_id=inspection.id).one()
        )
        enriched = verification_service.enrich_evaluation(
            session, evaluation, evaluation_out(evaluation)
        )
        assert enriched["officer_effective_status"] == "REVIEW_REQUIRED"
