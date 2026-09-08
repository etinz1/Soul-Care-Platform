"""
Risk Engine — deterministic clinical routing for the Smart Intake module.

DESIGN PRINCIPLE: This is safety-critical code. The hard-stop thresholds
below implement the *structural* logic requested (Safe-T / ACT routing for
suicidal ideation, immediate specialist routing for substance abuse) using
widely-recognized screener conventions (PHQ-9 item 9; a single-item
substance-use severity screen). The exact thresholds, the Safe-T Suicide
Assessment Five-Step Evaluation and Triage steps that follow a positive
screen, and the addiction-referral criteria MUST be reviewed and signed off
by a licensed clinical supervisor before this goes anywhere near real
clients. Nothing here should be read as clinical advice — it is the
software routing scaffold around a clinical decision that a licensed human
protocol (Safe-T / ACT) still owns.

This module has ONE job: given a validated IntakeSubmission, decide whether
a hard-stop protocol fires, and if so, hand back enough information for the
API layer to create the RiskEvent + Referral rows inside one transaction.
It does not touch the database itself, which keeps it unit-testable in
isolation.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import IntakeSubmission


# --- Thresholds (placeholders for clinical sign-off — see module docstring) ---
SUICIDAL_IDEATION_HARD_STOP_THRESHOLD = 1  # PHQ-9 item 9: ANY endorsement (>=1) triggers Safe-T
SUBSTANCE_ABUSE_HARD_STOP_THRESHOLD = 3  # 0-4 scale; >=3 triggers immediate specialist routing
SUBSTANCE_ABUSE_MODERATE_THRESHOLD = 1  # >=1 triggers a non-urgent addiction-counselor referral


@dataclass
class RiskAssessmentResult:
    is_hard_stop: bool
    risk_type: Optional[str] = None  # "suicidal_ideation" | "substance_abuse"
    severity: Optional[str] = None  # "low" | "moderate" | "high" | "imminent"
    protocol_triggered: str = "none"  # "safe_t" | "act_model" | "addiction_referral" | "none"
    routed_provider_type: Optional[str] = None  # matches ProviderType enum values
    referral_urgency: Optional[str] = None  # "standard" | "urgent" | "emergency"
    message: str = ""
    audit_reasons: list[str] = field(default_factory=list)


def evaluate(intake: IntakeSubmission) -> RiskAssessmentResult:
    """
    Evaluate an intake submission for hard-stop clinical conditions.

    Order of evaluation matters: suicidal ideation is checked first and, if
    triggered, short-circuits with the highest-severity routing regardless
    of other flags present, per the requirement that this be a genuine
    "hard stop" rather than one signal among several.
    """
    reasons: list[str] = []

    # --- 1. Suicidal ideation hard stop (Safe-T / ACT model) ---
    if intake.c9_suicidal_ideation >= SUICIDAL_IDEATION_HARD_STOP_THRESHOLD:
        severity = "imminent" if intake.c9_suicidal_ideation >= 2 else "high"
        reasons.append(
            f"PHQ-9 item 9 score={intake.c9_suicidal_ideation} "
            f">= threshold {SUICIDAL_IDEATION_HARD_STOP_THRESHOLD}"
        )
        return RiskAssessmentResult(
            is_hard_stop=True,
            risk_type="suicidal_ideation",
            severity=severity,
            protocol_triggered="safe_t",
            routed_provider_type="psychiatrist",
            referral_urgency="emergency" if severity == "imminent" else "urgent",
            message=(
                "Your responses indicate you may be having thoughts of self-harm. "
                "This is immediately and confidentially routed to a licensed psychiatrist "
                "on our clinical network. If you are in immediate danger, please call or "
                "text 988 (Suicide & Crisis Lifeline) or go to your nearest emergency room now."
            ),
            audit_reasons=reasons,
        )

    # --- 2. Substance abuse hard stop ---
    if intake.substance_use_severity >= SUBSTANCE_ABUSE_HARD_STOP_THRESHOLD:
        reasons.append(
            f"substance_use_severity={intake.substance_use_severity} "
            f">= threshold {SUBSTANCE_ABUSE_HARD_STOP_THRESHOLD}"
        )
        return RiskAssessmentResult(
            is_hard_stop=True,
            risk_type="substance_abuse",
            severity="high",
            protocol_triggered="addiction_referral",
            routed_provider_type="addiction_specialist",
            referral_urgency="urgent",
            message=(
                "Your responses indicate a pattern of substance use that calls for specialized "
                "support. You are being connected with an addiction specialist in our clinical "
                "network for prompt follow-up."
            ),
            audit_reasons=reasons,
        )

    # --- 3. Moderate substance-use signal: non-urgent specialist referral, not a hard stop ---
    if intake.substance_use_severity >= SUBSTANCE_ABUSE_MODERATE_THRESHOLD:
        reasons.append(
            f"substance_use_severity={intake.substance_use_severity} "
            f">= moderate threshold {SUBSTANCE_ABUSE_MODERATE_THRESHOLD}"
        )
        return RiskAssessmentResult(
            is_hard_stop=False,
            risk_type="substance_abuse",
            severity="moderate",
            protocol_triggered="none",
            routed_provider_type="addiction_specialist",
            referral_urgency="standard",
            message=(
                "Based on your responses, we recommend connecting with an addiction specialist "
                "alongside your coaching. Your coach will discuss this referral option with you."
            ),
            audit_reasons=reasons,
        )

    # --- 4. No hard-stop conditions ---
    return RiskAssessmentResult(
        is_hard_stop=False,
        message="Thank you for completing your intake. Your coach will review your responses shortly.",
        audit_reasons=["no risk thresholds met"],
    )
