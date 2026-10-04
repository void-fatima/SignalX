# Evaluation foundation

No real-provider evaluation has run. The 20-message demo is a synthetic
development fixture; it is not an independent test set and is not evidence of
precision/recall. Unit-test numbers below are deliberately artificial.

Setayesh owns labels, datasets, tuning and reports. Build ~50–60 development
messages and at least 100 held-out test messages by Day 4. Store labels separately
from message CSV; never send labels to the Agent. Keep conversations disjoint
between development and test. Tune on development only; record model/prompt/
score versions, provider_mode and sample count in the report.

The new CLI takes lists of JSON objects:

```json
[{"external_id":"example-1","conversation_id":"conversation-1","relevant":true}]
```

Predictions are exported by Roham's backend integration, preserving external_id:

```json
[{"external_id":"example-1","decision":"respond","is_candidate":true,"status":"completed"}]
```

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/evaluate.py --labels data/evaluation/test_labels.json --predictions data/evaluation/test_predictions.json --dev-labels data/evaluation/dev_labels.json --output data/evaluation/test_report.json
```

Those files are future dataset artifacts, not pre-created fixtures. The CLI
makes no provider calls and does not pretend to have evaluated the demo.

evaluate() rejects missing/extra predictions and duplicate IDs. `respond` is
predicted positive; `review` is not. Screened-out and failed messages stay in the
denominator. Failures cannot have a definitive decision; failed positive truths
count as FN and failed_count is shown. Precision/recall with zero denominators
are null. Unknown screening prevents reporting screening_recall as complete.
validate_split() rejects development/test conversation overlap when --dev-labels
is supplied; always supply it for the final held-out report.

Feedback acceptance is a separate operational statistic, not offline precision.
Mock and real runs, costs and reports must be separate. Latency measurements,
provider usage aggregation, labeling review and real test-set execution remain
tasks, not completed claims.
