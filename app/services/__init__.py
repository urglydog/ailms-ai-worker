"""Tang logic nghiep vu cua AI Worker.

Rong o Giai doan 0. Cac service duoc them theo giai doan:
  · Giai doan 5 — DubbingService (dieu phoi pipeline UC19)
  · Giai doan 7 — CreatorService (sinh hoc lieu UC25)
  · Giai doan 8 — TutorService (RAG UC30), DiscoveryService (UC49)

Quy tac (lms-ai-worker-rules): service KHONG import httpx truc tiep, chi goi qua
app/providers/. Service cung KHONG raise HTTPException — chi raise loi nghiep vu.
"""
