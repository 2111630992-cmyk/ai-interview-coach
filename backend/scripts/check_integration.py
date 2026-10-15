"""前后端联调检查：确认浏览器实际会走的路径是通的。

覆盖三件事（不需要浏览器）：
1. 前端 dev server 是否正常返回 SPA 外壳
2. Vite 能否按需编译入口模块
3. 后端 CORS 是否真的允许前端源（预检 + 实际请求 + SSE 端点）

用法：
    cd frontend && npm run dev                         # 终端 1
    cd backend  && uvicorn app.main:app --port 8000    # 终端 2
    python scripts/check_integration.py
"""

from __future__ import annotations

import sys

import httpx

FRONTEND = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
BACKEND = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}", flush=True)


def main() -> int:
    print(f"=== 联调检查：前端 {FRONTEND} <-> 后端 {BACKEND} ===\n", flush=True)

    # ---------- 1. 前端 SPA 外壳 ----------
    try:
        r = httpx.get(f"{FRONTEND}/", timeout=20)
        ok = r.status_code == 200 and 'id="root"' in r.text and "main.tsx" in r.text
        check(ok, f"前端返回 SPA 外壳（HTTP {r.status_code}）")
    except Exception as exc:
        check(False, f"前端不可达：{exc}")

    # ---------- 2. Vite 按需编译 ----------
    try:
        r = httpx.get(f"{FRONTEND}/src/main.tsx", timeout=30)
        ok = r.status_code == 200 and "createRoot" in r.text
        check(ok, f"Vite 能按需编译 main.tsx（HTTP {r.status_code}）")
    except Exception as exc:
        check(False, f"Vite 编译失败：{exc}")

    # ---------- 3. CORS 预检 ----------
    origin = FRONTEND
    cors_headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    try:
        pre = httpx.options(f"{BACKEND}/api/v1/auth/login", headers=cors_headers, timeout=20)
        allow = pre.headers.get("access-control-allow-origin")
        check(allow == origin, f"CORS 预检通过（allow-origin={allow}）")
    except Exception as exc:
        check(False, f"预检失败：{exc}")

    # ---------- 4. 实际请求带 CORS 响应头 ----------
    try:
        g = httpx.get(f"{BACKEND}/api/v1/health", headers={"Origin": origin}, timeout=20)
        allow = g.headers.get("access-control-allow-origin")
        check(allow == origin, f"实际请求带 CORS 响应头（allow-origin={allow}）")
        print(f"     health = {g.json()}", flush=True)
    except Exception as exc:
        check(False, f"实际请求失败：{exc}")

    # ---------- 5. SSE 端点可被跨域调用 ----------
    # 前端用 fetch + ReadableStream（而非 EventSource），因此同样依赖 CORS
    try:
        pre = httpx.options(
            f"{BACKEND}/api/v1/interviews/xxx/answer", headers=cors_headers, timeout=20
        )
        check(
            pre.headers.get("access-control-allow-origin") == origin,
            "SSE 端点允许跨域（前端用 fetch 读流，需要 CORS）",
        )
    except Exception as exc:
        check(False, f"SSE 预检失败：{exc}")

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n=== 联调检查：{passed}/{total} 通过 ===", flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
