"""Index embedding cho Tutor gọi batch, không gọi từng câu."""

from unittest.mock import AsyncMock, patch

from app.models import Segment
from app.services import tutor_indexing


async def test_index_segments_embeds_all_sentences_in_one_batch_call():
    segs = [Segment(seq=i, start=float(i), end=float(i) + 1, text=f"cau {i}") for i in range(3)]
    batch = AsyncMock(return_value=[[0.1], [0.2], [0.3]])
    single = AsyncMock()
    insert = AsyncMock()
    with patch("app.providers.gemini.embed_contents", batch), \
         patch("app.providers.gemini.embed_content", single), \
         patch("app.providers.supabase_vector.insert_embeddings", insert):
        await tutor_indexing.index_segments(7, "en", segs)

    batch.assert_awaited_once_with(["cau 0", "cau 1", "cau 2"])
    single.assert_not_awaited()
    rows = insert.await_args.args[0]
    assert [r.embedding for r in rows] == [[0.1], [0.2], [0.3]]
    assert [r.segment_id for r in rows] == [0, 1, 2]
