from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)


def CompactionCapability():
    # Context Window Compaction strategy
    # See: https://pydantic.dev/docs/ai/harness/compaction/
    return TieredCompaction(
        target_fraction=0.75,
        tiers=[
            # Tier 1: cheaply truncate pathological model responses or tool-call
            # arguments that could otherwise prevent later compaction from running.
            ClampOversizedMessages(max_part_tokens=50_000),
            # Tier 2: discard older tool results while preserving the three most
            # recent tool-call/result pairs. TieredCompaction invokes this directly,
            # so max_tokens only needs to satisfy the strategy's validation.
            ClearToolResults(max_tokens=1, keep_pairs=3),
            # Tier 3: if the first two tiers cannot reduce context below 75%,
            # summarize older history while retaining recent messages and the
            # original text of recent user messages.
            SummarizingCompaction(
                max_tokens=1,
                keep_messages=20,
                keep_user_messages=True,
            ),
        ],
    )
