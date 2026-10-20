import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def render_case(case, review):
    scenario = case["scenario"]
    lines = [
        f"## {scenario['id']}",
        "",
        f"Status: {case['status']}",
        "",
        "### Review expectations",
        "",
    ]
    lines.extend(f"- {item}" for item in scenario["expected_behavior"])
    lines.extend(
        [
            "",
            "### Supplied context",
            "",
            "```json",
            json.dumps(
                {key: scenario[key] for key in ("profile", "knowledge", "latest_summary")},
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "### Conversation",
            "",
        ]
    )
    for number, turn in enumerate(case["turns"], 1):
        lines.extend([f"**{number}. {turn['role']}**", "", turn["content"], ""])
    if case.get("error"):
        lines.extend([f"Generation error: {case['error']}", ""])
        if case.get("error_details"):
            lines.extend(["```json", json.dumps(case["error_details"], indent=2), "```", ""])
    lines.extend(
        ["### Reviews", "", "```json", json.dumps(review, ensure_ascii=False, indent=2), "```", ""]
    )
    return "\n".join(lines)


def render_report(directory):
    directory = Path(directory)
    run = read_json(directory / "run.json")
    reviews = read_json(directory / "reviews.json")
    lines = [
        "# Saarthi conversation review",
        "",
        f"Run: {run['id']} | Mode: {run['mode']} | Prompt: {run['prompt_sha256']}",
        "",
        f"Saarthi model: {run['model']} | Simulator: {run['simulator_model'] or 'replay'}",
        "",
        "Read REVIEW_GUIDE.md before judging. Human verdicts are final; blanks are unreviewed.",
        "Generation completion is not a quality pass. Turn numbers include the greeting.",
        "",
    ]
    for case_id in run["case_ids"]:
        case = read_json(directory / f"{case_id}.json")
        lines.append(render_case(case, reviews[case_id]))
    (directory / "report.md").write_text("\n".join(lines))


def compare_runs(before, after, destination):
    before, after, destination = Path(before), Path(after), Path(destination)
    old, new = read_json(before / "run.json"), read_json(after / "run.json")
    old_reviews, new_reviews = read_json(before / "reviews.json"), read_json(after / "reviews.json")
    lines = [
        "# Saarthi prompt comparison",
        "",
        f"Before: {old['id']} ({old['prompt_sha256']})",
        "",
        f"After: {new['id']} ({new['prompt_sha256']})",
        "",
        f"Models: {old['model']} -> {new['model']}",
        "",
        "Fresh simulations may take different paths. Replay fixes user messages, but those",
        "messages can become unnatural after a different assistant reply. Inspect both.",
        "",
    ]
    common = [case_id for case_id in old["case_ids"] if case_id in new["case_ids"]]
    if not common:
        raise ValueError("Runs have no scenarios in common")
    for case_id in common:
        a, b = read_json(before / f"{case_id}.json"), read_json(after / f"{case_id}.json")
        same_users = [t["content"] for t in a["turns"] if t["role"] == "user"] == [
            t["content"] for t in b["turns"] if t["role"] == "user"
        ]
        lines.extend(
            [
                f"# {case_id}",
                "",
                f"Identical user messages: {same_users}",
                "",
                f"Identical scenario/context: {a['scenario'] == b['scenario']}",
                "",
                "# Before",
                "",
                render_case(a, old_reviews[case_id]),
                "# After",
                "",
                render_case(b, new_reviews[case_id]),
            ]
        )
    missing = sorted(set(old["case_ids"]) ^ set(new["case_ids"]))
    if missing:
        lines.extend(["# Unmatched scenarios", "", ", ".join(missing), ""])
    destination.write_text("\n".join(lines))
