"""
UC-0A — Complaint Classifier
Lossless keyword classifier driven by agents.md enforcement rules and
skills.md `classify_complaint` + `batch_classify` skills.

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

SEVERITY_KEYWORDS = [
    "injury", "child", "school", "hospital", "ambulance",
    "fire", "hazard", "fell", "collapse",
]

CATEGORY_KEYWORDS = {
    "Flooding": ["flood", "waterlog", "knee-deep", "stranded", "submerged"],
    "Drain Blockage": ["drain", "blocked", "clogged", "blockage"],
    "Heat Hazard": [
        "heat", "temperature", "degrees", "°c", "melting",
        "burning", "burns", "hot", "unbearable", "storing heat",
        "unsafe", "dangerous", "44", "45", "52", "51", "50",
    ],
    "Heritage Damage": [
        "heritage", "historic", "monument", "step well", "temple",
        "museum", "old city", "heritage street",
    ],
    "Noise": ["music", "amplifier", "loud", "noisy", "audible", "club", "wedding band"],
    "Waste": [
        "waste", "garbage", "rubbish", "trash", "overflow", "litter",
        "dumped", "dumping", "debris", "bulk waste",
    ],
    "Streetlight": [
        "streetlight", "street light", "lights out", "lighting", "lamp",
        "substation", "darkness", "unlit", "sparking", "flickering",
        "electrical", "exposed to full sun",
    ],
    "Pothole": ["pothole"],
    "Road Damage": [
        "road", "cracked", "sinking", "subsidence", "buckled", "surface",
        "broken", "upturned", "footpath", "paving", "bubble",
        "asphalt", "tarmac", "pavement", "cobble", "cobblestone", "tiles",
        "tiles broken", "divider", "shelter", "bridge", "approach",
        "carriageway", "lane", "kerb", "manhole",
    ],
}


def classify_complaint(row: dict) -> dict:
    """Classify a single complaint row into category, priority, reason, flag."""
    complaint_id = row.get("complaint_id", "")
    description = (row.get("description") or "").lower()

    if not description.strip():
        return {
            "complaint_id": complaint_id,
            "category": "Other",
            "priority": "Standard",
            "reason": "Refused: description missing, cannot classify from description alone.",
            "flag": "NEEDS_REVIEW",
        }

    scores = {cat: [] for cat in CATEGORIES}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        matched = [kw for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\w*\b", description)]
        if matched:
            scores[cat] = matched

    scored = [(cat, len(keywords)) for cat, keywords in scores.items() if keywords]
    scored.sort(key=lambda x: (-x[1], x[0]))

    if not scored or scored[0][1] == 0:
        category = "Other"
        matched_keywords = []
        flag = "NEEDS_REVIEW"
    else:
        top_score = scored[0][1]
        top_cats = [c for c, s in scored if s == top_score]
        if len(top_cats) == 1:
            category = top_cats[0]
            matched_keywords = scores[category]
            # Ambiguous if a strong secondary category also matches.
            secondary = [c for c, s in scored if c != top_cats[0] and s >= top_score - 1 and s >= 2]
            flag = "NEEDS_REVIEW" if secondary else ""
        else:
            category = "Other"
            matched_keywords = []
            flag = "NEEDS_REVIEW"

    if any(kw in description for kw in SEVERITY_KEYWORDS):
        priority = "Urgent"
    else:
        priority = "Standard"

    if matched_keywords:
        cited = ", ".join(f"'{kw}'" for kw in matched_keywords[:4])
        reason = (
            f"Description cited {cited} → category {category}; "
            f"priority {priority}."
        )
    else:
        reason = (
            f"No category keywords matched clearly → category Other; "
            f"priority {priority}."
        )

    return {
        "complaint_id": complaint_id,
        "category": category,
        "priority": priority,
        "reason": reason,
        "flag": flag,
    }


def batch_classify(input_path: str, output_path: str):
    """Read input CSV, classify each row, write results CSV."""
    fieldnames = ["complaint_id", "category", "priority", "reason", "flag"]
    with open(input_path, newline="", encoding="utf-8") as fin, \
         open(output_path, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            result = classify_complaint(row)
            # Preserve original complaint_id even if column absent.
            if "complaint_id" not in row:
                result["complaint_id"] = row.get("complaint_id", "")
            writer.writerow(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UC-0A Complaint Classifier")
    parser.add_argument("--input", required=True, help="Path to test_[city].csv")
    parser.add_argument("--output", required=True, help="Path to write results CSV")
    args = parser.parse_args()
    batch_classify(args.input, args.output)
    print(f"Done. Results written to {args.output}")
