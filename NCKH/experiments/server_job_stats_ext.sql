-- =====================================================================
-- Số liệu lồng tiếng của KHOÁ HỌC THỬ NGHIỆM — CHỈ ĐỌC (SELECT). Bản mở rộng của server_job_stats.sql:
-- lọc theo danh sách ID bài học, thêm thời lượng bài, thời lượng audio cuối, thời gian từng đoạn.
-- KHÔNG chọn email/tên người dùng, KHÔNG chọn nội dung câu, KHÔNG chọn URL file (final_url) -> an toàn để lưu vào results/.
--
-- Cách chạy (Thiện tự nhập mật khẩu, mật khẩu không nằm trong lệnh hay lịch sử):
--   1) Sửa dòng SET @lesson_ids bên dưới thành ID các bài của khoá học tạm, vd '101,102,103,104'
--   2) cd /var/lms/ai-worker/NCKH/experiments && mkdir -p results/server_YYYYMMDD
--      read -rs MYSQL_PWD; export MYSQL_PWD
--      docker exec -i -e MYSQL_PWD lms_mysql mysql -u lms_user lms_db < server_job_stats_ext.sql > results/server_YYYYMMDD/out.tsv
--      unset MYSQL_PWD
--   3) python3 NCKH/experiments/analyze_server.py NCKH/experiments/results/server_YYYYMMDD/out.tsv
-- Các khối được đánh dấu bằng dòng "##<TÊN>" để analyze_server.py tách.
-- =====================================================================
SET SESSION TRANSACTION READ ONLY;
SET @lesson_ids = '2284,2285,2286,2287,2288';   -- khóa 92: lec01=2284, lec02=2285, lec03=2286, lec04=2288 (2287: bài trùng/đã xóa nếu có)

SELECT '##JOBS' AS section;
SELECT
    j.id AS job_id, j.lesson_id, j.target_language, j.status, j.total_chunks, j.done_chunks, j.retry_count,
    l.duration_sec AS lesson_duration_sec,
    j.created_at, j.started_at, j.finished_at,
    TIMESTAMPDIFF(SECOND, j.created_at, j.started_at)  AS queue_wait_sec,
    TIMESTAMPDIFF(SECOND, j.started_at, j.finished_at) AS processing_sec,
    (SELECT TIMESTAMPDIFF(SECOND, j.started_at, MIN(c.created_at))
       FROM audio_tracks t JOIN audio_chunks c ON c.audio_track_id = t.id
      WHERE t.lesson_id = j.lesson_id AND t.language = j.target_language AND c.created_at >= j.started_at) AS first_chunk_sec,
    LEFT(j.error_message, 200) AS error_message
FROM ai_jobs j JOIN lessons l ON l.id = j.lesson_id
WHERE j.job_type = 'DUBBING' AND FIND_IN_SET(j.lesson_id, @lesson_ids)
ORDER BY j.id;

SELECT '##JOB_CHUNKS' AS section;
SELECT jc.ai_job_id AS job_id, jc.chunk_index, jc.start_sec, jc.end_sec, jc.status, jc.retry_count,
       jc.created_at, jc.updated_at
FROM ai_job_chunks jc JOIN ai_jobs j ON j.id = jc.ai_job_id
WHERE FIND_IN_SET(j.lesson_id, @lesson_ids)
ORDER BY jc.ai_job_id, jc.chunk_index;

SELECT '##SEGMENTS' AS section;
SELECT tr.lesson_id, tr.language, s.seq, s.start_sec, s.end_sec, (s.end_sec - s.start_sec) AS t_orig,
       s.speech_rate, s.was_summarized, CHAR_LENGTH(s.text) AS tgt_chars
FROM transcripts tr JOIN transcript_segments s ON s.transcript_id = tr.id
WHERE tr.is_source = 0 AND FIND_IN_SET(tr.lesson_id, @lesson_ids)
ORDER BY tr.lesson_id, tr.language, s.seq;

SELECT '##TRACKS' AS section;
SELECT t.lesson_id, t.language, t.status, t.duration_sec AS track_duration_sec, l.duration_sec AS lesson_duration_sec,
       (t.duration_sec - l.duration_sec) AS diff_sec, t.file_size, t.play_count, t.voice_name
FROM audio_tracks t JOIN lessons l ON l.id = t.lesson_id
WHERE FIND_IN_SET(t.lesson_id, @lesson_ids)
ORDER BY t.lesson_id, t.language;

SELECT '##AUDIO_CHUNKS' AS section;
SELECT t.lesson_id, t.language, c.chunk_index, c.start_sec, c.end_sec, c.created_at
FROM audio_tracks t JOIN audio_chunks c ON c.audio_track_id = t.id
WHERE FIND_IN_SET(t.lesson_id, @lesson_ids)
ORDER BY t.lesson_id, t.language, c.chunk_index;
