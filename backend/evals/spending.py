"""Durable worst-case reservations for local experiments."""

import json
import urllib.request
from decimal import Decimal

from evals.artifacts import read_json, write_json


def account(settings):
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": "Bearer " + settings.openrouter_api_key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)["data"]
    return {k: float(data[k]) for k in ("total_credits", "total_usage")}


def remaining(balance):
    return Decimal(str(balance["total_credits"])) - Decimal(str(balance["total_usage"]))


class SpendingLimit(ValueError):
    pass


class Spending:
    def __init__(self, path, limit, candidates, *, round_directory=None):
        self.path, self.limit = path, Decimal(str(limit))
        if not self.limit.is_finite() or self.limit <= 0:
            raise ValueError("Budget must be positive and finite")
        self.candidates = {c["model"]: c for c in candidates}
        for candidate in candidates:
            for key in ("input_per_m", "output_per_m"):
                rate = Decimal(str(candidate[key]))
                if not rate.is_finite() or rate < 0:
                    raise ValueError("Prices must be nonnegative and finite")
        self.round_directory = round_directory
        self.records, self.label, self.pending = [], {}, None
        self.save()

    def save(self):
        write_json(
            self.path,
            {
                "limit_usd": str(self.limit),
                "reserved_usd": str(
                    sum((Decimal(r["reserved_usd"]) for r in self.records), Decimal(0))
                ),
                "policy": "Retain worst-case reservations even on failure/missing usage. Token costs are estimates, not billing; account delta is separate.",
                "calls": self.records,
            },
        )

    def before(self, settings, name, instruction, payload, schema):
        c = self.candidates[settings.agent_model]
        size = len(instruction.encode()) + len(json.dumps(payload, ensure_ascii=False).encode())
        if schema:
            size += len(json.dumps(schema.model_json_schema()).encode()) * 2
        bound = size + 4096  # UTF-8 bytes plus conservative ADK framing allowance.
        if bound >= 32000:
            raise SpendingLimit("Input exceeds reserved short-context tier")
        reserve = (
            Decimal(str(c["input_per_m"])) * bound
            + Decimal(str(c["output_per_m"])) * settings.agent_max_output_tokens
        ) / 1000000
        used = sum((Decimal(r["reserved_usd"]) for r in self.records), Decimal(0))
        if used + reserve > self.limit:
            raise SpendingLimit("Next request would exceed stage budget")
        if self.round_directory is not None:
            others = sum(
                (
                    Decimal(read_json(p)["reserved_usd"])
                    for p in self.round_directory.rglob("spending.json")
                    if p.resolve() != self.path.resolve()
                ),
                Decimal(0),
            )
            # Sequential runs only: all stage ledgers remain inside one round directory.
            if others + used + reserve > Decimal("4"):
                raise SpendingLimit("Next request would exceed the $4 round budget")
        self.pending = {
            **self.label,
            "model": settings.agent_model,
            "agent": name,
            "input_token_upper_bound": bound,
            "reserved_usd": str(reserve),
            "status": "reserved",
            "usage": {},
            "estimated_token_cost_usd": None,
        }
        self.records.append(self.pending)
        self.save()
        return {
            "temperature": (0.2 if schema else 0.7) if c["temperature"] else None,
            "provider": {
                "only": [c["provider"]],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {
                    "prompt": c["input_per_m"],
                    "completion": c["output_per_m"],
                    "request": 0,
                },
            },
        }

    def after(self, record):
        self.pending.update(record)
        c, usage = self.candidates[record["model"]], record["usage"]
        if all(k in usage for k in ("prompt_tokens", "completion_tokens")):
            value = (
                Decimal(usage["prompt_tokens"]) * Decimal(str(c["input_per_m"]))
                + Decimal(usage["completion_tokens"]) * Decimal(str(c["output_per_m"]))
            ) / 1000000
            self.pending["estimated_token_cost_usd"] = str(value)
            if (
                usage["prompt_tokens"] > self.pending["input_token_upper_bound"]
                or usage["completion_tokens"] > record["max_output_tokens"]
            ):
                self.save()
                raise SpendingLimit("Usage exceeded reservation assumptions; stop")
        self.save()
