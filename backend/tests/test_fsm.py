from app.causal.fsm import FSMState, Signals, transition


def s(severity="INFO", action_active=False, recovering=False):
    return Signals(severity=severity, action_active=action_active, recovering=recovering)


def test_normal_escalation_paths():
    assert transition(FSMState.NORMAL, s("WARN")).state is FSMState.AT_RISK
    assert transition(FSMState.NORMAL, s("CRITICAL")).state is FSMState.CRITICAL
    assert transition(FSMState.NORMAL, s("INFO")).changed is False


def test_at_risk_transitions():
    assert transition(FSMState.AT_RISK, s("CRITICAL")).state is FSMState.CRITICAL
    assert transition(FSMState.AT_RISK, s("INFO")).state is FSMState.NORMAL
    assert transition(FSMState.AT_RISK, s("WARN")).changed is False


def test_critical_requires_action_to_mitigate():
    assert transition(FSMState.CRITICAL, s("CRITICAL")).state is FSMState.CRITICAL
    assert (
        transition(FSMState.CRITICAL, s("CRITICAL", action_active=True)).state
        is FSMState.MITIGATING
    )


def test_mitigating_resolves_or_recovers():
    assert transition(FSMState.MITIGATING, s("INFO")).state is FSMState.NORMAL
    assert (
        transition(FSMState.MITIGATING, s("CRITICAL", action_active=True, recovering=True)).state
        is FSMState.RECOVERING
    )
    # mitigation disengaged while still critical → back to CRITICAL
    assert (
        transition(FSMState.MITIGATING, s("CRITICAL", action_active=False)).state
        is FSMState.CRITICAL
    )


def test_recovering_relapse_and_clear():
    assert transition(FSMState.RECOVERING, s("CRITICAL")).state is FSMState.CRITICAL
    assert transition(FSMState.RECOVERING, s("INFO")).state is FSMState.NORMAL
