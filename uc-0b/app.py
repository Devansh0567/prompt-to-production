"""
UC-0B — Summary That Changes Meaning
Lossless policy summarizer driven by agents.md enforcement rules and
skills.md `retrieve_policy` + `summarize_policy` skills.

Run:
    python app.py --input ../data/policy-documents/policy_hr_leave.txt --output summary_hr_leave.txt
"""
import argparse
import re
import sys

CLAUSE_RE = re.compile(r"^(\d+\.\d+)\s+(.*)", re.MULTILINE)


def _is_separator(line: str) -> bool:
    return len(line) >= 20 and not re.search(r"[A-Za-z0-9]", line)


_SECTION_RE = re.compile(r"^\d+\.\s+[A-Z][A-Z\s&().\-',\"]+$")


def _is_section_header(line: str) -> bool:
    return bool(_SECTION_RE.match(line))


def retrieve_policy(input_path: str):
    """Loads a plain text policy document and parses it into structured,
    numbered clauses. (skill: retrieve_policy)"""
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise ValueError(f"Refused: policy file not found: {input_path}")
    except OSError:
        raise ValueError(f"Refused: policy file unreadable: {input_path}")

    clauses = []
    current = None
    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = CLAUSE_RE.match(line)
        if m:
            if current is not None:
                clauses.append(current)
            current = {"clause": m.group(1), "text": m.group(2).strip()}
        elif current is not None:
            if _is_separator(line) or _is_section_header(line):
                continue
            current["text"] += " " + line
    if current is not None:
        clauses.append(current)

    if not clauses:
        raise ValueError(
            "Refused: policy document lacks clear clause numbers."
        )
    return {"source": input_path, "clauses": clauses}


def _is_multi_condition(text: str) -> bool:
    return bool(re.search(r"\b(and|AND)\b.*\b(Head|Director|Manager|Commissioner)", text)) or \
           bool(re.search(r"(Department Head and HR Director|both .* and)", text, re.IGNORECASE))


def summarize_policy(policy: dict) -> str:
    """Produces a lossless summary preserving every numbered clause, binding
    verbs, multi-condition rules and required approvers. (skill: summarize_policy)"""
    clauses = policy["clauses"]
    source = policy["source"]

    lines = []
    lines.append("=" * 70)
    lines.append("SUMMARY — " + source)
    lines.append("=" * 70)
    lines.append("")
    lines.append("Enforcement rules applied (per uc-0b/agents.md):")
    lines.append("  1. Every numbered clause from the source is present.")
    lines.append("  2. Multi-condition obligations preserve ALL conditions/approvers.")
    lines.append("  3. No information added beyond the source document.")
    lines.append("  4. All clauses quoted verbatim; multi-condition clauses flagged.")
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"TOTAL CLAUSES PRESERVED: {len(clauses)}")
    lines.append("-" * 70)
    lines.append("")

    flagged = []
    for c in clauses:
        clause_id = c["clause"]
        text = c["text"]
        entry = f"Clause {clause_id}:\n  {text}"
        if _is_multi_condition(text):
            flagged.append(clause_id)
            entry += "\n  [FLAGGED: multi-condition obligation — preserved verbatim, ALL approvers/conditions intact]"
        lines.append(entry)
        lines.append("")

    if flagged:
        lines.append("-" * 70)
        lines.append("MULTI-CONDITION CLAUSES VERBATIM (no condition dropped):")
        for cid in flagged:
            matched = next(c for c in clauses if c["clause"] == cid)
            lines.append(f"  Clause {cid}: {matched['text']}")
        lines.append("-" * 70)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="UC-0B — Lossless Policy Summarizer")
    parser.add_argument("--input", required=True, help="Path to policy .txt file")
    parser.add_argument("--output", required=True, help="Path to write summary")
    args = parser.parse_args()

    policy = retrieve_policy(args.input)
    summary = summarize_policy(policy)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary written to {args.output} ({len(policy['clauses'])} clauses preserved)")


if __name__ == "__main__":
    main()
