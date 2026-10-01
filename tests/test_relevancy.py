from research_scout.agents.relevancy import LlamaScorer
from research_scout.models import Item, Profile


class _Reply:
    def __init__(self, payload):
        self.payload = payload
        self.user = ""

    def chat_json(self, system, user, task=""):
        self.user = user
        return self.payload


def _profile() -> Profile:
    return Profile(
        username="a",
        domain="regulatory publishing",
        research_interests="eCTD",
        goals="faster submissions",
        key_skills="writing",
        created_at="2026-01-01T00:00:00Z",
    )


def test_scores_blogs_by_item_number_not_url():
    long_url = "url:https://example.com/blog/3-tips-to-save-time-in-regulatory-submissions"
    blog = Item(
        kind="blog",
        canonical_id=long_url,
        title="3 tips to save time in regulatory submissions",
        source="example.com",
        url="https://example.com/blog/3-tips-to-save-time-in-regulatory-submissions",
        excerpt="Practical notes on eCTD publishing.",
        query="regulatory",
    )
    paper = Item(
        kind="paper",
        canonical_id="doi:10.1000/reg.1",
        title="eCTD implementation",
        source="openalex",
        url="https://doi.org/10.1000/reg.1",
        excerpt="A study of eCTD.",
        query="eCTD",
    )
    reply = _Reply(
        {
            "scores": [
                {"n": 1, "score": 84, "band": "direct", "reason": "practical regulatory notes"},
                {"n": "2", "score": 40, "band": "weak", "reason": "off topic"},
            ]
        }
    )
    LlamaScorer(reply).score_batch(_profile(), [blog, paper])

    assert "n=1" in reply.user
    assert long_url not in reply.user
    assert blog.relevancy_score == 84
    assert blog.band == "direct"
    assert blog.reason == "practical regulatory notes"
    assert paper.relevancy_score == 40
    assert paper.reason == "off topic"
