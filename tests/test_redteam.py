"""The red-team gate runs in CI through pytest too, so a change that lets a known attack through fails the build."""

from hotelplatform import redteam

from scripts import run_redteam


def test_shared_corpus_passes_through_this_app_and_no_new_gaps():
    shared, own = run_redteam.run()
    assert redteam.score(shared)["passed"] == len(shared)
    failing = {r.case.id for r in own if not r.passed}
    assert failing <= run_redteam.known_gaps(), f"new red-team failures: {failing - run_redteam.known_gaps()}"
    assert len(shared) + len(own) >= 25


def test_benign_controls_are_never_blocked():
    shared, own = run_redteam.run()
    assert all(r.passed for r in shared + own if r.case.expect == "allow")
