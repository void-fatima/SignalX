# Evaluation artifacts — Setayesh

Place these real labeling/evaluation artifacts here as that work is performed:

- dev_messages.csv / dev_labels.json (~50–60 synthetic development messages)
- test_messages.csv / test_labels.json (at least 100 held-out messages)
- test_predictions.json / test_report.json (actual provider run)

CSV headers match data/demo_messages.csv. Labels are separate JSON arrays with
external_id, conversation_id, relevant. Never put labels in Agent input. Keep
conversations disjoint between dev/test. Predictions and CLI usage are documented
in docs/evaluation.md. This directory deliberately contains no invented dataset
or generated performance report.
