"""Prompt versioning trên Langfuse: tạo v1/v2, chạy sample trace, promote/rollback.

Cách dùng (từ repo root, trong venv, .env đã có key project Langfuse cá nhân):

    .venv/Scripts/python scripts/prompt_versioning.py init
    .venv/Scripts/python scripts/prompt_versioning.py run --label baseline
    .venv/Scripts/python scripts/prompt_versioning.py run --label candidate
    .venv/Scripts/python scripts/prompt_versioning.py promote
    .venv/Scripts/python scripts/prompt_versioning.py run --label production
    .venv/Scripts/python scripts/prompt_versioning.py rollback
    .venv/Scripts/python scripts/prompt_versioning.py run --label production

Ghi chú: lệnh `run` gọi chính `LabAgent.run` (cùng code path với API) với
`LANGFUSE_PROMPT_LABEL` được đặt theo label cần demo; trace ID được in ra để
đối chiếu trên UI và ghi vào report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from langfuse import get_client  # noqa: E402

PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
BASE_URL = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

V1_TEXT = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2_TEXT = V1_TEXT + "\nAnswer concisely: at most two short sentences."
PROMPT_CONFIG = {"variables": ["feature", "docs", "message"]}

SAMPLE_MESSAGES = (
    "What is your refund policy?",
    "Explain why metrics traces and logs work together",
)


def _api_keypair() -> tuple[str, str]:
    return os.getenv("LANGFUSE_PUBLIC_KEY", ""), os.getenv("LANGFUSE_SECRET_KEY", "")


def _find_existing(client, text: str) -> int | None:
    """Tìm version có nội dung đúng bằng text (idempotent init)."""
    page = client.api.prompts.list()
    for meta in page.data:
        if meta.name != PROMPT_NAME:
            continue
        for v in meta.versions:
            try:
                p = client.api.prompts.get(prompt_name=PROMPT_NAME, version=v)
            except Exception:
                continue
            if p.prompt == text:
                return v
    return None


def ensure_prompts(client) -> None:
    """Tạo (idempotent) v1 labels [baseline, production] và v2 label [candidate].

    Nếu nội dung prompt đã tồn tại thì tái sử dụng version cũ thay vì tạo version mới.
    """
    existing_v1 = _find_existing(client, V1_TEXT)
    if existing_v1 is not None:
        p1_version = existing_v1
    else:
        p1 = client.create_prompt(
            name=PROMPT_NAME,
            prompt=V1_TEXT,
            type="text",
            config=PROMPT_CONFIG,
            commit_message="CP2: v1 baseline prompt",
        )
        p1_version = int(p1.version)
    client.update_prompt(name=PROMPT_NAME, version=p1_version, new_labels=["baseline", "production"])

    existing_v2 = _find_existing(client, V2_TEXT)
    if existing_v2 is not None:
        p2_version = existing_v2
    else:
        p2 = client.create_prompt(
            name=PROMPT_NAME,
            prompt=V2_TEXT,
            type="text",
            config=PROMPT_CONFIG,
            commit_message="CP2: v2 concise-answer format",
        )
        p2_version = int(p2.version)
    client.update_prompt(name=PROMPT_NAME, version=p2_version, new_labels=["candidate"])
    print(f"[init] v1 -> version {p1_version}, labels [baseline, production]")
    print(f"[init] v2 -> version {p2_version}, labels [candidate]")


def get_version_by_label(client, label: str) -> int:
    p = client.get_prompt(PROMPT_NAME, label=label, type="text")
    return int(p.version)


def promote(client) -> None:
    v1, v2 = get_version_by_label(client, "baseline"), get_version_by_label(client, "candidate")
    client.update_prompt(name=PROMPT_NAME, version=v1, new_labels=["baseline"])
    client.update_prompt(name=PROMPT_NAME, version=v2, new_labels=["candidate", "production"])
    print(f"[promote] production: v{v1} -> v{v2} (baseline giữ v{v1}, candidate giữ v{v2})")


def rollback(client) -> None:
    v1, v2 = get_version_by_label(client, "baseline"), get_version_by_label(client, "candidate")
    client.update_prompt(name=PROMPT_NAME, version=v2, new_labels=["candidate"])
    client.update_prompt(name=PROMPT_NAME, version=v1, new_labels=["baseline", "production"])
    print(f"[rollback] production: v{v2} -> v{v1}")


def run_sample(label: str) -> None:
    """Chạy 2 request mẫu qua LabAgent với label đã chọn, in trace ID ra."""
    os.environ["LANGFUSE_PROMPT_LABEL"] = label
    from app.agent import LabAgent

    agent = LabAgent()
    for i, message in enumerate(SAMPLE_MESSAGES):
        correlation_id = f"pv-{label}-{i:02d}"
        result = agent.run(
            user_id=f"u_pv_{label}",
            feature="qa",
            session_id=f"s_pv_{label}_{i}",
            message=message,
            correlation_id=correlation_id,
        )
        print(f"[run:{label}] corr={correlation_id} latency={result.latency_ms}ms cost={result.cost_usd}")
    time.sleep(5)  # chờ SDK flush

    pk, sk = _api_keypair()
    now = dt.datetime.now(dt.timezone.utc)
    frm = now - dt.timedelta(minutes=2)
    r = httpx.get(
        f"{BASE_URL}/api/public/v2/observations",
        auth=(pk, sk),
        params={
            "limit": "20",
            "type": "AGENT",
            "fromStartTime": frm.isoformat(),
            "toStartTime": now.isoformat(),
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[run:{label}] WARNING: không query được trace ID ({r.status_code})")
        return
    rows = sorted(r.json().get("data", []), key=lambda o: o.get("timestamp") or o.get("startTime") or "")
    print(f"[run:{label}] trace IDs (2 trace gần nhất, correlation pv-{label}-00/01):")
    for o in rows[-2:]:
        print(f"    traceId={o.get('traceId')} ts={o.get('timestamp') or o.get('startTime')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Tạo prompt v1/v2 với labels đúng")
    sub.add_parser("promote", help="Chuyển label production sang v2")
    sub.add_parser("rollback", help="Đưa label production về v1")
    p_run = sub.add_parser("run", help="Chạy 2 request mẫu với label đã chọn")
    p_run.add_argument("--label", default="production", choices=["baseline", "candidate", "production"])
    args = parser.parse_args()

    client = get_client()
    if client.auth_check() is False:
        raise SystemExit("[fail] Langfuse auth thất bại — kiểm tra key/base_url trong .env")
    print("[ok] Kết nối Langfuse thành công")

    if args.cmd == "init":
        ensure_prompts(client)
    elif args.cmd == "promote":
        promote(client)
    elif args.cmd == "rollback":
        rollback(client)
    elif args.cmd == "run":
        # CHỈ init khi prompt chưa tồn tại — nếu gọi ensure_prompts mỗi lần run,
        # label sẽ bị reset về mặc định và xóa tác dụng promote/rollback.
        try:
            client.get_prompt(PROMPT_NAME, label="baseline", type="text")
            prompts_exist = True
        except Exception:
            prompts_exist = False
        if not prompts_exist:
            ensure_prompts(client)
        run_sample(args.label)


if __name__ == "__main__":
    main()
