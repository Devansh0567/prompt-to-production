"""
UC-0A — Complaint Classifier
Keyword classifier driven by uc-0a/agents.md enforcement rules and
uc-0a/skills.md `classify_complaint` + `batch_classify` skills.

NOTE: uc-0b/agents.md + uc-0b/skills.md govern policy summarization
(UC-0B) and do not apply here. This module follows the UC-0A taxonomy,
severity keywords, and refusal rules instead.

Run:
    python classifier.py --input ../data/city-test-files/test_pune.csv --output results_pune.csv
"""
import argparse
import csv
import re

CATEGORIES = [
    "Pothole", "Flooding", "Streetlight", "Waste", "Noise",
    "Road Damage", "Heritage Damage", "Heat Hazard", "Drain Blockage", "Other",
]

# Exact severity list per uc-0a/README.md + uc-0a/agents.md (substring match).
SEVERITY_KEYWORDS = [
    "injury", "child", "school", "hospital", "ambulance",
    "fire", "hazard", "fell", "collapse",
]

# Specific-signal keywords only. Generic location words ("road", "street",
# "lane", "bridge", "shelter", "public road") deliberately score NOTHING —
# they caused false ties -> spurious Other/NEEDS_REVIEW.
CATEGORY_PATTERNS = {
    "Pothole": [r"pothole"],
    "Flooding": [
        r"flood", r"waterlog", r"knee-?deep", r"stranded", r"submerged",
        r"rainwater", r"abandoned",
    ],
    "Drain Blockage": [r"drain", r"block(?:ed|age|ing)?", r"clogged"],
    "Heat Hazard": [
        r"heat(?:wave|ing)?", r"temperatur", r"degrees?", r"\d+\s*°?c\b",
        r"melt(?:ing)?", r"burn(?:ing|s)?", r"unbearable",
        r"storing heat", r"\b44\b", r"\b45\b", r"\b50\b", r"\b51\b", r"\b52\b",
    ],
    "Noise": [
        r"music", r"amplifier", r"\bloud\b", r"nois[ey]", r"audible",
        r"\bclub\b", r"wedding band", r"drilling", r"idling", r"engines?",
    ],
    "Waste": [
        r"waste", r"garbage", r"rubbish", r"trash", r"overflow",
        r"litter", r"dump(?:ed|ing)?", r"debris",
        r"not (?:cleared|removed)", r"dead animal",
    ],
    "Streetlight": [
        r"streetlight", r"street light", r"lamp post", r"lights? out",
        r"\blamp\b", r"substation", r"darkness", r"unlit",
        r"sparking", r"flickering", r"wiring theft",
    ],
    # Road Damage requires a DAMAGE verb/noun — bare "road" never counts.
    "Road Damage": [
        r"cracked", r"sinking", r"subsid(?:ed|ence|ent)?", r"buckled",
        r"collaps(?:ed|e)?", r"crater", r"swallowed",
        r"broken", r"upturned", r"bubbl(?:ing|e)?",
        r"footpath", r"paving", r"cobble(?:stone)?s?",
        r"manhole", r"tiles?", r"kerb", r"carriageway",
    ],
}

# Heritage Damage requires heritage noun + damage verb together, OR a strong
# standalone heritage-damage phrase. Location-only mentions
# ("heritage zone garbage", "heritage precinct" with noise) score 0.
_HERITAGE_NOUNS = [
    r"heritage", r"historic", r"monument", r"step well", r"temple",
    r"museum", r"old city", r"ancient", r"heritage stone",
    r"heritage street", r"heritage building",
]
_HERITAGE_DAMAGE_VERBS = [
    r"knocked over", r"not restored", r"broken up", r"defaced",
    r"not replaced", r"removed", r"damage", r"subsid(?:ed|ence|ent)?",
    r"billboard", r"concern",
]

# "debris" is ambiguous (construction debris blocking a drain = Drain, not
# Waste). Drain wins that duel via precedence below.
_PRECEDENCE = [
    "Pothole", "Flooding", "Drain Blockage", "Heat Hazard",
    "Streetlight", "Noise", "Waste", "Road Damage", "Heritage Damage",
]


def _find_cited_words(description: str, patterns) -> list:
    """Return actual substrings from the description matching patterns.

    Overlapping matches are deduped: a match fully contained inside an
    already-counted span (e.g. 'lamp' inside 'lamp post') is skipped so
    generic sub-words cannot inflate a category's score into a false tie.
    """
    cited = []
    spans = []
    for pat in patterns:
        m = re.search(pat, description, re.IGNORECASE)
        if m:
            span = m.span()
            if any(s <= span[0] and span[1] <= e for s, e in spans):
                continue
            spans.append(span)
            cited.append(m.group(0))
    return cited


def _score(description: str) -> dict:
    """Score each category by count of distinct specific-signal matches."""
    scores = {}
    matched = {}
    scores["Heritage Damage"] = 0
    matched["Heritage Damage"] = []
    for cat, patterns in CATEGORY_PATTERNS.items():
        words = _find_cited_words(description, patterns)
        # "broken"/"removed" alone (shelter glass, irrigation) need a road-ish
        # anchor to count as Road Damage; otherwise they are ambiguous noise.
        if cat == "Road Damage" and words:
            anchors = re.search(
                r"road|footpath|pav|surface|tarmac|cobble|tile|kerb|manhole|"
                r"carriageway|bridge approach|crater|subsiden|swallowed",
                description, re.IGNORECASE,
            )
            generic_only = all(
                re.fullmatch(r"broken|removed", w, re.IGNORECASE) for w in words
            )
            if generic_only and not anchors:
                words = []
        scores[cat] = len(words)
        matched[cat] = words

    # Heritage Damage: special combo rule (noun + damage verb required,
    # except strong standalone nouns like monument/step well/museum damage
    # which are handled by the noun list + verb list overlap).
    heritage_noun = any(
        re.search(p, description, re.IGNORECASE) for p in _HERITAGE_NOUNS
    )
    heritage_verb = any(
        re.search(p, description, re.IGNORECASE) for p in _HERITAGE_DAMAGE_VERBS
    )
    if heritage_noun and heritage_verb:
        if scores["Heritage Damage"] == 0:
            scores["Heritage Damage"] = 3  # strong combo signal: beats generic overlap
            matched["Heritage Damage"] = _find_cited_words(
                description, _HERITAGE_NOUNS + _HERITAGE_DAMAGE_VERBS
            )
    else:
        # Location-only heritage mention: not damage. Kill weak single hits
        # (e.g. "heritage precinct" alongside a Noise action).
        if scores["Heritage Damage"] <= 1 and any(
            re.search(p, description, re.IGNORECASE)
            for p in [r"heritage (?:zone|precinct|area)"]
        ):
            scores["Heritage Damage"] = 0
            matched["Heritage Damage"] = []

    # Debris + drain context belongs to Drain Blockage, not Waste.
    if re.search(r"drain", description, re.IGNORECASE) and re.search(
        r"block|debris|clog", description, re.IGNORECASE
    ):
        scores["Waste"] = 0
        matched["Waste"] = [
            w for w in matched["Waste"] if not re.fullmatch(r"debris", w, re.IGNORECASE)
        ]
        if not matched["Waste"]:
            scores["Waste"] = 0

    return scores, matched


def classify_complaint(row: dict) -> dict:
    """Classify a single complaint row (skill: classify_complaint)."""
    complaint_id = row.get("complaint_id", "")
    raw_description = row.get("description") or ""
    description = raw_description.strip()

    if not description:
        return {
            "complaint_id": complaint_id,
            "category": "Other",
            "priority": "Standard",
            "reason": "Refused: description missing, cannot classify from description alone.",
            "flag": "NEEDS_REVIEW",
        }

    lowered = description.lower()
    scores, matched = _score(description)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_score = ranked[0][1]
    leaders = [cat for cat, s in ranked if s == top_score and s > 0]

    if not leaders:
        category = "Other"
        cited_words = []
        flag = "NEEDS_REVIEW"
    elif len(leaders) == 1:
        category = leaders[0]
        cited_words = matched[category]
        flag = ""
    else:
        # Genuine tie: resolve via precedence only when the winner is
        # strictly more specific (Pothole over Road Damage style). A tie
        # between two strong (>=2) distinct signals stays ambiguous.
        strong = [c for c in leaders if scores[c] >= 2]
        if len(strong) == 1:
            category = strong[0]
            cited_words = matched[category]
            flag = ""
        else:
            ordered = sorted(leaders, key=lambda c: _PRECEDENCE.index(c))
            # Pothole/Flooding/Drain specificity wins over generic overlap
            # only when the runner-up signal is weak (score 1) and the
            # winner's signal words are present verbatim.
            if scores[ordered[0]] > 0 and scores.get(ordered[1], 0) <= 1 and (
                ordered[0] in ("Pothole", "Flooding", "Drain Blockage", "Heat Hazard")
                or scores[ordered[0]] >= 2
            ):
                # Still ambiguous if BOTH are strong specific claims
                # (e.g. heritage damage verb + road subsidence verb).
                if scores[ordered[0]] >= 2 and scores.get(ordered[1], 0) >= 2:
                    category = "Other"
                    cited_words = []
                    flag = "NEEDS_REVIEW"
                else:
                    category = ordered[0]
                    cited_words = matched[category]
                    flag = ""
            else:
                category = "Other"
                cited_words = []
                flag = "NEEDS_REVIEW"

    if any(kw in lowered for kw in SEVERITY_KEYWORDS):
        priority = "Urgent"
    else:
        priority = "Standard"

    if category == "Other" and not cited_words:
        reason = (
            "No specific category keywords matched clearly in "
            f"'{description[:60]}' so category Other with priority {priority}."
        )
    else:
        cited = ", ".join(f"'{w}'" for w in cited_words[:4])
        reason = (
            f"Cited {cited} in description so category {category} "
            f"with priority {priority}."
        )
    # Keep reason to a single sentence.
    reason = reason.strip()
    if reason.count(".") > 1:
        reason = reason.split(".")[0] + "."

    return {
        "complaint_id": complaint_id,
        "category": category,
        "priority": priority,
        "reason": reason,
        "flag": flag,
    }


def batch_classify(input_path: str, output_path: str):
    """Read input CSV, classify each row, write results CSV (skill: batch_classify)."""
    fieldnames = ["complaint_id", "category", "priority", "reason", "flag"]
    with open(input_path, newline="", encoding="utf-8") as fin, \
         open(output_path, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            try:
                result = classify_complaint(row)
            except Exception:
                result = {
                    "complaint_id": row.get("complaint_id", ""),
                    "category": "Other",
                    "priority": "Standard",
                    "reason": "Refused: row failed to classify, flagged for review.",
                    "flag": "NEEDS_REVIEW",
                }
            writer.writerow(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UC-0A Complaint Classifier")
    parser.add_argument("--input", required=True, help="Path to test_[city].csv")
    parser.add_argument("--output", required=True, help="Path to write results CSV")
    args = parser.parse_args()
    batch_classify(args.input, args.output)
    print(f"Done. Results written to {args.output}")
