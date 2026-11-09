-- =====================================================================
-- Số liệu lồng tiếng từ database MySQL của server — CHỈ ĐỌC (SELECT).
-- Dùng cho mục "Thời gian xử lý" và "Phân bố tốc độ đọc trong vận hành thật".
-- Chạy thủ công:  mysql -h <host> -u <user> -p <db> < server_job_stats.sql
-- Hoặc dùng server_job_stats.py để xuất ra CSV.
-- =====================================================================
SET SESSION TRANSACTION READ ONLY;

-- [jobs] 1 dòng / job lồng tiếng: thời gian xử lý và thời gian ra đoạn đầu tiên
SELECT
    j.id                          AS job_id,
    j.lesson_id,
    j.target_language,
    j.status,
    j.total_chunks,
    j.done_chunks,
    j.retry_count,
    l.duration_sec                AS lesson_duration_sec,
    j.created_at,
    j.started_at,
    j.finished_at,
    TIMESTAMPDIFF(SECOND, j.created_at, j.started_at)  AS queue_wait_sec,
    TIMESTAMPDIFF(SECOND, j.started_at, j.finished_at) AS processing_sec,
    (SELECT TIMESTAMPDIFF(SECOND, j.started_at, MIN(c.created_at))
       FROM audio_tracks t JOIN audio_chunks c ON c.audio_track_id = t.id
      WHERE t.lesson_id = j.lesson_id AND t.language = j.target_language
        AND c.created_at >= j.started_at)            AS first_chunk_sec
FROM ai_jobs j
JOIN lessons l ON l.id = j.lesson_id
WHERE j.job_type = 'DUBBING'
ORDER BY j.id;

-- [segments] 1 dòng / câu đã lồng tiếng (bản dịch, is_source = 0):
-- speech_rate là hệ số tốc độ đã áp dụng, was_summarized cho biết câu có bị LLM rút gọn
SELECT
    tr.lesson_id,
    tr.language,
    s.seq,
    s.start_sec,
    s.end_sec,
    (s.end_sec - s.start_sec)     AS t_orig,
    s.speech_rate,
    s.was_summarized,
    CHAR_LENGTH(s.text)           AS tgt_chars
FROM transcripts tr
JOIN transcript_segments s ON s.transcript_id = tr.id
WHERE tr.is_source = 0
ORDER BY tr.lesson_id, tr.language, s.seq;

-- [reuse] Mức tái sử dụng: số học viên/lượt phát dùng chung 1 bản lồng tiếng
SELECT
    t.lesson_id,
    t.language,
    t.status,
    t.duration_sec,
    t.play_count
FROM audio_tracks t
ORDER BY t.lesson_id, t.language;
