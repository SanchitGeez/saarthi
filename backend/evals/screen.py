"""Frozen-prefix experiments through the actual product reply; no simulator."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from agents import runner, saarthi
from config import Settings
from evals.artifacts import read_json, write_json
from evals.spending import Spending, SpendingLimit, account, remaining

ROOT = Path(__file__).parent


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def checkpoint(settings, prompt, fixture):
    payload = fixture["payload"]
    transport = fixture.get("transport", "text")
    if transport not in {"text", "voice"}:
        raise ValueError("Checkpoint transport must be text or voice")
    fields = {"profile", "knowledge", "latest_summary", "opening", "transcript"}
    if transport == "voice" and "voice_recovery" in payload:
        fields.add("voice_recovery")
    if set(payload) != fields:
        raise ValueError("Checkpoint must contain exactly product context fields")
    transcript = payload["transcript"]
    if transport == "voice" and "voice_recovery" in payload:
        if (
            not transcript
            or transcript[-1].get("interrupted") is not True
            or transcript[-1]["role"] != "assistant"
        ):
            raise ValueError("Voice recovery must end with the delivered assistant prefix")
        transcript = transcript[:-1]
    if not transcript or transcript[-1]["role"] != "user":
        raise ValueError("Checkpoint must end with latest user message")
    if transport == "voice":
        return "".join([chunk async for chunk in saarthi.stream(settings, payload, prompt=prompt)])
    return await saarthi.reply(settings, payload, prompt=prompt)


def report(directory, records):
    lines = [
        "# Frozen-prefix responses",
        "",
        "Read inputs in fixtures.json. No simulator or regeneration of earlier replies.",
        "",
        "Candidate identities: key.json. Review first before opening the key.",
        "",
    ]
    lines.extend(
        [
            f"Replies: {sum(r['status'] == 'completed' for r in records)} completed / "
            f"{len(records)} attempted. Completion is not a quality pass.",
            "",
        ]
    )
    for r in records:
        lines += [
            f"## {r['sample']} / {r['checkpoint']} / repeat {r['repeat']}",
            "",
            r.get("response") or f"Generation failed: {r.get('error', 'interrupted')}",
            "",
        ]
    (directory / "report.md").write_text("\n".join(lines))


def run(args):
    settings = Settings()
    balance = account(settings)
    if remaining(balance) < args.budget:
        raise ValueError("Verified balance below requested stage budget")
    candidates = read_json(args.plan)["candidates"]
    if args.model:
        candidates = [c for c in candidates if c["id"] in args.model]
        if {c["id"] for c in candidates} != set(args.model):
            raise ValueError("Unknown candidate")
    fixtures = read_json(args.fixtures)
    if args.case:
        if set(args.case) - {f["id"] for f in fixtures}:
            raise ValueError("Unknown checkpoint")
        fixtures = [f for f in fixtures if f["id"] in args.case]
    if not fixtures or not candidates:
        raise ValueError("No inputs selected")
    prompt, directory = args.prompt.read_text(), args.output
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "prompt.txt").write_text(prompt)
    write_json(directory / "fixtures.json", fixtures)
    write_json(directory / "key.json", {f"candidate-{i + 1}": c for i, c in enumerate(candidates)})
    write_json(directory / "plan.json", read_json(args.plan))
    sources = directory / "sources"
    sources.mkdir()
    for file in (
        Path(runner.__file__),
        Path(saarthi.__file__),
        Path(__file__),
        ROOT / "spending.py",
    ):
        (sources / file.name).write_text(file.read_text())
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "frozen-prefix",
        "balance_before": balance,
        "budget_usd": args.budget,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "fixtures_sha256": digest(fixtures),
        "status": "running",
        "repeats": args.repeats,
        "max_output_tokens": args.cap,
        "timeout_seconds": 60,
        "versions": {name: version(name) for name in ("google-adk", "litellm", "deepeval")},
    }
    write_json(directory / "run.json", metadata)
    spending, records = (
        Spending(
            directory / "spending.json", args.budget, candidates, round_directory=directory.parent
        ),
        [],
    )
    try:
        with runner.observe_calls(spending.before, spending.after):
            for i, c in enumerate(candidates):
                configured = settings.model_copy(
                    update={
                        "agent_model": c["model"],
                        "agent_reasoning_effort": c["effort"],
                        "agent_max_output_tokens": args.cap,
                        "agent_timeout_seconds": 60,
                    }
                )
                first, incompatible = True, False
                for repeat in range(1, args.repeats + 1):
                    for fixture in fixtures:
                        spending.label = {
                            "sample": f"candidate-{i + 1}",
                            "checkpoint": fixture["id"],
                            "repeat": repeat,
                            "payload_sha256": digest(fixture["payload"]),
                        }
                        record = {**spending.label, "status": "running"}
                        records.append(record)
                        write_json(directory / "responses.json", records)
                        print(c["id"], fixture["id"], repeat, flush=True)
                        try:
                            record["response"] = asyncio.run(
                                checkpoint(configured, prompt, fixture)
                            )
                            record["status"] = "completed"
                        except runner.AgentFailure as exc:
                            record.update(
                                status="failed", error=exc.code, error_details=exc.details
                            )
                            incompatible = first
                        finally:
                            first = False
                            write_json(directory / "responses.json", records)
                            report(directory, records)
                        if incompatible:
                            break
                    if incompatible:
                        break
        metadata["status"] = (
            "completed_with_failures"
            if any(r["status"] != "completed" for r in records)
            else "completed"
        )
    except (SpendingLimit, KeyboardInterrupt):
        metadata["status"] = "stopped"
        raise
    except BaseException:
        metadata["status"] = "failed"
        raise
    finally:
        for record in records:
            if record["status"] == "running":
                record["status"] = "interrupted"
        write_json(directory / "responses.json", records)
        try:
            after = account(settings)
            metadata.update(
                balance_after=after,
                account_usage_delta_usd=after["total_usage"] - balance["total_usage"],
            )
        except Exception:
            metadata["balance_after"] = None
        write_json(directory / "run.json", metadata)
        report(directory, records)
    print("Review", directory / "report.md", flush=True)
    return 1 if metadata["status"] != "completed" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "screen-plan.json")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "checkpoints.json")
    parser.add_argument("--prompt", type=Path, default=ROOT / "prompts/grounded-v4.txt")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=1)
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--cap", type=int, choices=[4096, 8192], default=4096)
    parser.add_argument("--model", action="append")
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not 0 < args.budget <= 4:
        parser.error("Stage budget must be above zero and at most $4")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
