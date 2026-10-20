import argparse
import asyncio
import hashlib
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from uuid import uuid4

from agents import runner, saarthi
from config import Settings
from evals.artifacts import compare_runs, read_json, render_report, write_json
from evals.models import Assessment, Scenario

ROOT = Path(__file__).parent


def load_scenarios(path):
    scenarios = [Scenario.model_validate(item) for item in read_json(path)]
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Scenario IDs must be unique")
    return scenarios


def git_revision():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def run_experiment(args, *, settings=None, simulator_settings=None, transport_metadata=None):
    from evals.simulation import SIMULATOR_INSTRUCTION, replay, simulate

    settings = settings or Settings()
    if not settings.openrouter_api_key:
        raise ValueError("Set OPENROUTER_API_KEY in backend/.env or the environment")
    if args.simulator_model and not args.simulator_model.startswith("openrouter/"):
        raise ValueError("Simulator model must use an openrouter/ model ID")
    simulator_settings = simulator_settings or settings.model_copy(
        update={
            "agent_model": args.simulator_model or settings.agent_model,
            "agent_provider": None if args.simulator_model else settings.agent_provider,
        }
    )
    source = Path(args.replay) if args.replay else None
    if source:
        previous = read_json(source / "run.json")
        originals = {key: read_json(source / f"{key}.json") for key in previous["case_ids"]}
        scenarios = [Scenario.model_validate(item["scenario"]) for item in originals.values()]
        if any(item["status"] != "completed" for item in originals.values()):
            raise ValueError("Replay requires a completed source run; rerun failed scenarios first")
    else:
        scenarios = load_scenarios(args.scenarios)
        scenarios = [s for s in scenarios if args.split == "all" or s.split == args.split]
    if args.case:
        wanted = set(args.case)
        if wanted - {s.id for s in scenarios}:
            raise ValueError("Requested case is absent from the selected split/source")
        scenarios = [s for s in scenarios if s.id in wanted]
    if not scenarios:
        raise ValueError("No scenarios selected")
    prompt = Path(args.prompt).read_text() if args.prompt else saarthi.PROMPT
    if not prompt.strip():
        raise ValueError("Prompt must not be blank")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    directory = Path(args.output) if args.output else ROOT / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "prompt.txt").write_text(prompt)
    (directory / "simulator.txt").write_text(SIMULATOR_INSTRUCTION)
    (directory / "REVIEW_GUIDE.md").write_text((ROOT / "REVIEW_GUIDE.md").read_text())
    sources = directory / "sources"
    sources.mkdir()
    for file in (Path(saarthi.__file__), Path(runner.__file__), ROOT / "simulation.py"):
        (sources / file.name).write_text(file.read_text())
    metadata = {
        "id": run_id,
        "mode": "replay" if source else "simulation",
        "source_run": str(source.resolve()) if source else None,
        "created_at": datetime.now(UTC).isoformat(),
        "git_revision": git_revision(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "model": settings.agent_model,
        "agent_provider": settings.agent_provider,
        "simulator_provider": None if source else simulator_settings.agent_provider,
        "simulator_model": None if source else simulator_settings.agent_model,
        "agent_temperature": runner.generation_temperature(settings),
        "simulator_temperature": None
        if source
        else runner.generation_temperature(simulator_settings, True),
        "max_output_tokens": settings.agent_max_output_tokens,
        "reasoning_effort": settings.agent_reasoning_effort,
        "timeout_seconds": settings.agent_timeout_seconds,
        "versions": {name: version(name) for name in ("deepeval", "google-adk", "litellm")},
        "case_ids": [s.id for s in scenarios],
        "status": "running",
    }
    metadata.update(transport_metadata or {})
    write_json(directory / "run.json", metadata)
    write_json(
        directory / "reviews.json", {s.id: {"human": None, "codex-sol": None} for s in scenarios}
    )
    for scenario in scenarios:
        write_json(
            directory / f"{scenario.id}.json",
            {"scenario": scenario.model_dump(mode="json"), "status": "pending", "turns": []},
        )
    print(f"Saving to {directory}", flush=True)
    failed = False
    try:
        for scenario in scenarios:
            path = directory / f"{scenario.id}.json"
            case = read_json(path)
            case["status"] = "running"
            case["max_user_turns"] = (
                sum(t["role"] == "user" for t in originals[scenario.id]["turns"])
                if source
                else args.max_turns or scenario.max_user_turns
            )
            write_json(path, case)

            def checkpoint(turns):
                case["turns"] = [{"role": t.role, "content": t.content} for t in turns]
                write_json(path, case)

            print(f"Running {scenario.id}", flush=True)
            case_started = monotonic()
            try:
                if source:
                    test_case = asyncio.run(
                        replay(
                            settings, scenario, prompt, originals[scenario.id]["turns"], checkpoint
                        )
                    )
                else:
                    test_case = simulate(
                        settings, simulator_settings, scenario, prompt, checkpoint, args.max_turns
                    )
                case.update(status="completed", deepeval_test_case=test_case)
            except Exception as exc:
                details = (
                    dict(exc.details)
                    if isinstance(exc, runner.AgentFailure)
                    else {
                        "code": "eval_error",
                        "message": "The evaluation harness raised an exception.",
                        "exception_chain": [type(exc).__name__],
                    }
                )
                details.update(
                    phase=(
                        "opening"
                        if not case["turns"]
                        else "assistant_reply"
                        if case["turns"][-1]["role"] == "user"
                        else "user_simulation"
                    ),
                    transcript_messages=len(case["turns"]),
                    case_elapsed_ms=round((monotonic() - case_started) * 1000),
                )
                case.update(status="failed", error=type(exc).__name__, error_details=details)
                failed = True
                print(f"  failed: {details['code']} ({details['phase']})", flush=True)
            finally:
                write_json(path, case)
                render_report(directory)
    except KeyboardInterrupt:
        metadata["status"] = "interrupted"
        case["status"] = "interrupted"
        write_json(path, case)
        raise
    finally:
        if metadata["status"] == "running":
            metadata["status"] = "failed" if failed else "completed"
        write_json(directory / "run.json", metadata)
        render_report(directory)
    print(f"Review {directory / 'report.md'}", flush=True)
    return 1 if failed else 0


def record_review(args):
    directory = Path(args.run)
    reviews = read_json(directory / "reviews.json")
    if args.case not in reviews:
        raise ValueError("Case not found in this run")
    assessment = Assessment(
        verdict=args.verdict, evidence=args.evidence, desired_change=args.change, flags=args.flag
    )
    reviews[args.case][args.reviewer] = assessment.model_dump()
    write_json(directory / "reviews.json", reviews)
    render_report(directory)


def main():
    parser = argparse.ArgumentParser(description="Local Saarthi conversation experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List scenarios without making model calls")
    listing.add_argument("--scenarios", type=Path, default=ROOT / "scenarios.json")
    run = commands.add_parser("run", help="Generate full conversations; makes provider calls")
    run.add_argument("--scenarios", type=Path, default=ROOT / "scenarios.json")
    run.add_argument("--split", choices=["development", "holdout", "all"], default="development")
    run.add_argument("--case", action="append", help="Repeat to select multiple cases")
    run.add_argument("--prompt", type=Path, help="Candidate prompt; defaults to the product prompt")
    run.add_argument(
        "--simulator-model", help="OpenRouter model for users; defaults to AGENT_MODEL"
    )
    run.add_argument("--max-turns", type=int, help="User-turn cap, excluding the opening greeting")
    run.add_argument(
        "--replay", type=Path, help="Reuse a run's user messages, bypassing simulation"
    )
    run.add_argument("--output", type=Path, help="New directory; existing directories are refused")
    review = commands.add_parser("review", help="Record one human or Codex/Sol assessment")
    review.add_argument("run", type=Path)
    review.add_argument("--case", required=True)
    review.add_argument("--reviewer", choices=["human", "codex-sol"], default="human")
    review.add_argument("--verdict", choices=["good", "acceptable", "bad"], required=True)
    review.add_argument("--evidence", required=True)
    review.add_argument("--change", required=True)
    review.add_argument(
        "--flag",
        action="append",
        default=[],
        choices=["invented_scripture", "wrong_citation", "harmful_agreement", "other"],
    )
    report = commands.add_parser("report", help="Refresh report after editing reviews.json")
    report.add_argument("run", type=Path)
    compare = commands.add_parser("compare", help="Write a local before/after review document")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run" and args.max_turns is not None and not 1 <= args.max_turns <= 20:
        parser.error("--max-turns must be between 1 and 20")
    if args.command == "run" and args.replay and (args.max_turns or args.simulator_model):
        parser.error("Replay reuses user turns; --max-turns and --simulator-model do not apply")
    try:
        if args.command == "list":
            for scenario in load_scenarios(args.scenarios):
                print(
                    f"{scenario.id}: {scenario.split}, {scenario.language}, "
                    f"up to {scenario.max_user_turns} user turns"
                )
        elif args.command == "run":
            return run_experiment(args)
        elif args.command == "review":
            record_review(args)
        elif args.command == "report":
            render_report(args.run)
        else:
            compare_runs(args.before, args.after, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
