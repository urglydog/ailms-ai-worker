-- Xóa bản lồng tiếng + bản ký âm + bản dịch của 4 bài thử nghiệm (khóa 92) để đo "lần lồng tiếng đầu".
-- Thứ tự theo NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md mục 6.3. Xóa CẢ transcript nguồn và đích
-- (giữ transcript đích sẽ lỗi 500 Duplicate entry uk_segment_transcript_seq — bẫy job 37).
-- CHỈ dùng cho đúng 4 lesson dưới đây. Đã được Sang cho phép (22/11/2026).
--
-- Chạy (người đo tự nhập mật khẩu MySQL khi được hỏi):
--   docker exec -i lms_mysql mysql -u <user> -p <db> < NCKH/experiments/reset_lessons.sql

-- 0. Xem trước (ghi kết quả vào NOTES)
SELECT 'ai_jobs' AS bang, lesson_id, COUNT(*) AS n FROM ai_jobs WHERE lesson_id IN (2284,2285,2286,2288) GROUP BY lesson_id
UNION ALL SELECT 'audio_tracks', lesson_id, COUNT(*) FROM audio_tracks WHERE lesson_id IN (2284,2285,2286,2288) GROUP BY lesson_id
UNION ALL SELECT 'transcripts', lesson_id, COUNT(*) FROM transcripts WHERE lesson_id IN (2284,2285,2286,2288) GROUP BY lesson_id;

START TRANSACTION;
DELETE FROM ai_job_chunks      WHERE ai_job_id IN (SELECT id FROM (SELECT id FROM ai_jobs WHERE lesson_id IN (2284,2285,2286,2288)) t);
DELETE FROM ai_jobs            WHERE lesson_id IN (2284,2285,2286,2288);
DELETE FROM audio_chunks       WHERE audio_track_id IN (SELECT id FROM (SELECT id FROM audio_tracks WHERE lesson_id IN (2284,2285,2286,2288)) t);
DELETE FROM audio_tracks       WHERE lesson_id IN (2284,2285,2286,2288);
DELETE FROM transcript_segments WHERE transcript_id IN (SELECT id FROM (SELECT id FROM transcripts WHERE lesson_id IN (2284,2285,2286,2288)) t);
DELETE FROM transcripts        WHERE lesson_id IN (2284,2285,2286,2288);
COMMIT;

-- 1. Kiểm tra sau khi xóa: phải ra 0 dòng
SELECT 'ai_jobs' AS bang, COUNT(*) FROM ai_jobs WHERE lesson_id IN (2284,2285,2286,2288)
UNION ALL SELECT 'audio_tracks', COUNT(*) FROM audio_tracks WHERE lesson_id IN (2284,2285,2286,2288)
UNION ALL SELECT 'transcripts', COUNT(*) FROM transcripts WHERE lesson_id IN (2284,2285,2286,2288);
