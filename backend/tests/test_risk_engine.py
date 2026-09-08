import uuid

from app.schemas import IntakeSubmission, PresentingConcern
from app.services import risk_engine


def _submission(**overrides):
    defaults = dict(
        client_id=uuid.uuid4(),
        distress_level=5,
        c9_suicidal_ideation=0,
        substance_use_severity=0,
        presenting_concerns=[PresentingConcern.anxiety],
    )
    defaults.update(overrides)
    return IntakeSubmission(**defaults)


def test_any_suicidal_ideation_endorsement_is_a_hard_stop():
    result = risk_engine.evaluate(_submission(c9_suicidal_ideation=1))
    assert result.is_hard_stop is True
    assert result.risk_type == "suicidal_ideation"
    assert result.protocol_triggered == "safe_t"
    assert result.routed_provider_type == "psychiatrist"
    assert result.severity == "high"


def test_higher_suicidal_ideation_score_is_imminent_severity():
    result = risk_engine.evaluate(_submission(c9_suicidal_ideation=3))
    assert result.severity == "imminent"
    assert result.referral_urgency == "emergency"


def test_suicidal_ideation_takes_priority_over_substance_abuse():
    result = risk_engine.evaluate(
        _submission(c9_suicidal_ideation=1, substance_use_severity=4)
    )
    assert result.risk_type == "suicidal_ideation"


def test_high_substance_use_is_a_hard_stop_routed_to_addiction_specialist():
    result = risk_engine.evaluate(_submission(substance_use_severity=3))
    assert result.is_hard_stop is True
    assert result.risk_type == "substance_abuse"
    assert result.routed_provider_type == "addiction_specialist"
    assert result.protocol_triggered == "addiction_referral"


def test_moderate_substance_use_is_a_referral_but_not_a_hard_stop():
    result = risk_engine.evaluate(_submission(substance_use_severity=1))
    assert result.is_hard_stop is False
    assert result.risk_type == "substance_abuse"
    assert result.severity == "moderate"


def test_no_risk_signals_returns_no_hard_stop():
    result = risk_engine.evaluate(_submission())
    assert result.is_hard_stop is False
    assert result.risk_type is None
    assert result.protocol_triggered == "none"
