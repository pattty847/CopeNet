from copenet.browser_agent.models import ElementBox
from copenet.browser_agent.observer import score_element


def test_search_input_ranks_above_skip_link() -> None:
    skip_score = score_element(
        role="link",
        text="Skip to content",
        aria_label="",
        placeholder="",
        box=ElementBox(x=0, y=0, width=10, height=10),
    )
    search_score = score_element(
        role="input",
        text="",
        aria_label="Search GitHub",
        placeholder="Search or jump to...",
        box=ElementBox(x=10, y=40, width=200, height=32),
    )
    assert search_score > skip_score
