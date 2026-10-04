"""Evaluate JSON files exported by the backend owner; no provider calls or labels in prompts."""
import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.agents.evaluation import Label, Prediction, evaluate, validate_split


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--dev-labels", type=Path, help="Check no conversation overlaps with test labels")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    labels = [Label.model_validate(row) for row in json.loads(args.labels.read_text(encoding="utf-8"))]
    predictions = [Prediction.model_validate(row) for row in json.loads(args.predictions.read_text(encoding="utf-8"))]
    if args.dev_labels:
        dev = [Label.model_validate(row) for row in json.loads(args.dev_labels.read_text(encoding="utf-8"))]
        validate_split(dev, labels)
    report = evaluate(labels, predictions).model_dump_json(indent=2)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
