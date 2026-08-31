from itertools import pairwise

import pytest

from competitor_scout.models.intelligence import RunType, ScoutRunStatus
from competitor_scout.schemas.runs import transition_allowed

ALLOWED_TRANSITIONS = {
    ScoutRunStatus.QUEUED: {
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.PLANNING: {
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.GATHERING: {
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.SYNTHESIZING: {
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
}


@pytest.mark.parametrize("current", list(ScoutRunStatus))
@pytest.mark.parametrize("target", list(ScoutRunStatus))
def test_full_run_transition_matrix(
    current: ScoutRunStatus,
    target: ScoutRunStatus,
) -> None:
    if target in ALLOWED_TRANSITIONS.get(current, set()):
        assert transition_allowed(current, target)
    else:
        with pytest.raises(ValueError, match="invalid Scout Run transition"):
            transition_allowed(current, target)


def test_daily_run_path() -> None:
    path = [
        ScoutRunStatus.QUEUED,
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
    ]
    assert all(transition_allowed(current, target) for current, target in pairwise(path))


def test_source_discovery_path_can_complete_after_gathering() -> None:
    path = [
        ScoutRunStatus.QUEUED,
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.COMPLETED,
    ]
    assert all(transition_allowed(current, target) for current, target in pairwise(path))


def test_source_discovery_can_complete_from_single_main_agent_step() -> None:
    assert transition_allowed(ScoutRunStatus.PLANNING, ScoutRunStatus.COMPLETED)
    assert transition_allowed(ScoutRunStatus.PLANNING, ScoutRunStatus.PARTIAL)


def test_weekly_brief_path_skips_gathering() -> None:
    path = [
        ScoutRunStatus.QUEUED,
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
    ]
    assert all(transition_allowed(current, target) for current, target in pairwise(path))


@pytest.mark.parametrize("run_type", [RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT])
def test_daily_and_manual_runs_cannot_bypass_research(
    run_type: RunType,
) -> None:
    assert transition_allowed(
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.GATHERING,
        run_type=run_type,
    )
    with pytest.raises(ValueError):
        transition_allowed(
            ScoutRunStatus.PLANNING,
            ScoutRunStatus.SYNTHESIZING,
            run_type=run_type,
        )
    with pytest.raises(ValueError):
        transition_allowed(
            ScoutRunStatus.PLANNING,
            ScoutRunStatus.COMPLETED,
            run_type=run_type,
        )


def test_source_discovery_uses_its_own_terminal_path() -> None:
    assert transition_allowed(
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.GATHERING,
        run_type=RunType.SOURCE_DISCOVERY,
    )
    assert transition_allowed(
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.COMPLETED,
        run_type=RunType.SOURCE_DISCOVERY,
    )
    with pytest.raises(ValueError):
        transition_allowed(
            ScoutRunStatus.GATHERING,
            ScoutRunStatus.SYNTHESIZING,
            run_type=RunType.SOURCE_DISCOVERY,
        )


def test_weekly_brief_cannot_take_daily_or_discovery_shortcuts() -> None:
    assert transition_allowed(
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.SYNTHESIZING,
        run_type=RunType.WEEKLY_BRIEF,
    )
    for invalid_target in (ScoutRunStatus.GATHERING, ScoutRunStatus.COMPLETED):
        with pytest.raises(ValueError):
            transition_allowed(
                ScoutRunStatus.PLANNING,
                invalid_target,
                run_type=RunType.WEEKLY_BRIEF,
            )


@pytest.mark.parametrize(
    "terminal",
    [ScoutRunStatus.COMPLETED, ScoutRunStatus.PARTIAL, ScoutRunStatus.FAILED],
)
@pytest.mark.parametrize("target", list(ScoutRunStatus))
def test_terminal_states_are_immutable(
    terminal: ScoutRunStatus,
    target: ScoutRunStatus,
) -> None:
    with pytest.raises(ValueError, match="invalid Scout Run transition"):
        transition_allowed(terminal, target)
