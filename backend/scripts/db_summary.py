"""打印 dev.db 里的演示数据概况（本地调试用）。

用法：python scripts/db_summary.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "dev.db")

if not DB.exists():
    print(f"{DB} 不存在，先跑一次服务或 scripts/e2e_check.py")
    raise SystemExit(1)

conn = sqlite3.connect(DB)

print(f"=== {DB} ===")
for email, nickname, is_guest in conn.execute(
    "select email, nickname, is_guest from users order by created_at"
):
    role = "游客" if is_guest else "正式"
    print(f"用户[{role}] {email}  ({nickname})")

for label, sql in [
    ("简历", "select count(*) from resumes"),
    ("岗位 JD", "select count(*) from job_descriptions"),
    ("匹配分析", "select count(*) from match_analyses"),
    ("面试会话", "select count(*) from interview_sessions"),
    ("已完成面试", "select count(*) from interview_sessions where status='finished'"),
    ("问答轮次", "select count(*) from turns"),
    ("已评分轮次", "select count(*) from turns where evaluation is not null"),
    ("面试报告", "select count(*) from reports"),
]:
    print(f"{label}: {conn.execute(sql).fetchone()[0]}")

rows = conn.execute(
    "select r.verdict, round(s.total_score, 1), r.dimension_scores "
    "from reports r join interview_sessions s on s.id = r.session_id"
).fetchall()
for verdict, score, dims in rows:
    print(f"报告: verdict={verdict} total={score} dims={dims}")
