from src.analysis.scoring import ScoreInputs, importance_score


def test_importance_score_is_weighted_and_clamped() -> None:
    score = importance_score(
        ScoreInputs(
            direct_relevance=100,
            materiality=100,
            source_reliability=80,
            recency=80,
            novelty=50,
            market_reaction=70,
            long_term_impact=90,
            multi_asset_impact=40,
            association_confidence=90,
        )
    )

    assert score == 82

