# skills.md — UC-0A Complaint Classifier

skills:
  - name: classify_complaint
    description: Classifies one complaint row into category, priority, reason, and flag using its description text.
    input: A single complaint row (dict with at least complaint_id and description).
    output: Dict with keys complaint_id, category, priority, reason, flag matching the UC-0A schema exactly.
    error_handling: On missing/blank description returns category: Other, priority: Standard, flag: NEEDS_REVIEW with a refusal reason; never crashes.

  - name: batch_classify
    description: Reads an input CSV of complaints, applies classify_complaint per row, and writes a results CSV with the same schema.
    input: Path to input CSV (test_[city].csv) and path to write results CSV.
    output: results_[city].csv with columns complaint_id, category, priority, reason, flag.
    error_handling: Continues processing if a row fails; still produces the output CSV with failed rows flagged NEEDS_REVIEW.
