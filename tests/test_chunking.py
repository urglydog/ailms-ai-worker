"""BR-CHUNK-02 — phân đoạn cố định N phút, phân đoạn cuối chứa phần dư."""

from app.services.dubbing_service import ChunkPlan, split_into_chunks


def test_split_into_chunks_exact_multiple():
    chunks = split_into_chunks(1200, chunk_minutes=10)  # 20 phut = dung 2 chunk 10 phut
    assert chunks == [ChunkPlan(0, 0, 600), ChunkPlan(1, 600, 1200)]


def test_split_into_chunks_last_chunk_has_remainder():
    chunks = split_into_chunks(930, chunk_minutes=10)  # 15 phut 30s
    assert chunks == [ChunkPlan(0, 0, 600), ChunkPlan(1, 600, 930)]
    assert chunks[-1].end_sec - chunks[-1].start_sec == 330


def test_split_into_chunks_shorter_than_one_chunk():
    chunks = split_into_chunks(90, chunk_minutes=10)  # BR-CHUNK-01: toi thieu 60s
    assert chunks == [ChunkPlan(0, 0, 90)]


def test_split_into_chunks_max_duration_180_minutes():
    chunks = split_into_chunks(180 * 60, chunk_minutes=10)
    assert len(chunks) == 18
    assert chunks[-1].end_sec == 180 * 60


def test_split_into_chunks_zero_duration_does_not_crash():
    chunks = split_into_chunks(0, chunk_minutes=10)
    assert chunks == [ChunkPlan(0, 0, 0)]
