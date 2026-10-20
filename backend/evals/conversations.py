"""Budgeted full conversations with independently fixed simulator settings."""

import argparse
from pathlib import Path
from types import SimpleNamespace

from agents import runner
from config import Settings
from evals.__main__ import run_experiment
from evals.artifacts import read_json, write_json
from evals.spending import Spending, account, remaining

ROOT = Path(__file__).parent


def run(args):
    base = Settings()
    balance = account(base)
    if remaining(balance) < args.budget:
        raise ValueError("Verified balance below stage budget")
    candidates = read_json(args.plan)["candidates"]
    assistant = next(c for c in candidates if c["id"] == args.model)
    simulator = next(c for c in candidates if c["id"] == args.simulator)
    # Separate settings: the simulator never inherits assistant effort/cap.
    settings = base.model_copy(
        update={
            "agent_model": assistant["model"],
            "agent_provider": assistant["provider"],
            "agent_reasoning_effort": assistant["effort"],
            "agent_max_output_tokens": 4096,
            "agent_timeout_seconds": 60,
        }
    )
    simulator_settings = base.model_copy(
        update={
            "agent_model": simulator["model"],
            "agent_provider": simulator["provider"],
            "agent_reasoning_effort": simulator["effort"],
            "agent_max_output_tokens": 2048,
            "agent_timeout_seconds": 60,
        }
    )
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "plan.json", read_json(args.plan))
    ledger = Spending(
        args.output / "spending.json",
        args.budget,
        [assistant, simulator],
        round_directory=args.output.parent,
    )
    result = None
    try:
        with runner.observe_calls(ledger.before, ledger.after):
            result = run_experiment(
                SimpleNamespace(
                    simulator_model=simulator["model"],
                    replay=None,
                    scenarios=args.scenarios,
                    split=args.split,
                    case=args.case,
                    prompt=args.prompt,
                    output=args.output / "conversations",
                    max_turns=6,
                ),
                settings=settings,
                simulator_settings=simulator_settings,
                transport_metadata={
                    "agent_temperature": 0.7 if assistant["temperature"] else None,
                    "simulator_temperature": 0.2 if simulator["temperature"] else None,
                    "simulator_reasoning_effort": simulator["effort"],
                    "simulator_max_output_tokens": 2048,
                    "assistant_provider": assistant["provider"],
                    "simulator_provider": simulator["provider"],
                    "spending_ledger": "../spending.json",
                },
            )
    finally:
        after = account(base)
        write_json(
            args.output / "billing.json",
            {
                "before": balance,
                "after": after,
                "account_usage_delta_usd": after["total_usage"] - balance["total_usage"],
            },
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--simulator", default="qwen/qwen3.7-flash")
    parser.add_argument("--plan", type=Path, default=ROOT / "screen-plan.json")
    parser.add_argument("--scenarios", type=Path, default=ROOT / "scenarios.json")
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 < args.budget <= 2:
        parser.error("Conversation stage limit must be above zero and at most $2")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
