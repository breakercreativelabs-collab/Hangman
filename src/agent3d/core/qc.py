"""Shared QC framework: numeric checks, negative tests, test logger, report summary.

Each check = one row in its module's/project's QC_RULES.md (same ID). Every check is a dict:
id, name, value, threshold, passed, context. Negative test = scene/file deliberately broken; the `required` checks must fail.
"""
import json
import os
import time
from dataclasses import dataclass, field


def check(id_, name, value, passed, threshold, context=""):
    if isinstance(value, float):
        value = round(value, 4)
    return dict(id=id_, name=name, value=value, threshold=threshold, passed=bool(passed), context=context)


def iou(a, b):
    """Intersection over union of two boolean masks."""
    return float((a & b).sum() / max((a | b).sum(), 1))


def caught(result, required):
    """A negative test is caught if every `required` item failed. Required item: 'ID' (some check with that ID failed) or
    'ID:name' (exactly that check failed). Returns (caught, sorted list of failed IDs)."""
    failed = {c["id"] for c in result if not c["passed"]}
    failed_names = {f"{c['id']}:{c['name']}" for c in result if not c["passed"]}
    return all(w in failed_names if ":" in w else w in failed for w in required), sorted(failed)


@dataclass
class NegativeTests:
    """One negative test: name, how to break things (parameter or function), checks that MUST fail."""
    name: str
    corrupt: object
    required: list = field(default_factory=list)


class Logger:
    """Test result logger (verb tests, negative tests, structure tests): print each row, summarize, write JSON."""

    def __init__(self):
        self.result, self.t0 = [], time.time()

    def test(self, name, condition, detail=""):
        self.result.append(dict(test=name, passed=bool(condition), detail=str(detail)))
        print(("  OK  " if condition else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))
        return bool(condition)

    @property
    def passed(self):
        return sum(h["passed"] for h in self.result)

    @property
    def duration(self):
        return time.time() - self.t0

    @property
    def all_passed(self):
        return self.passed == len(self.result)

    def write(self, path, **extra):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = dict(passed=self.all_passed, count=len(self.result), **extra,
                    seconds=round(time.time() - self.t0, 1), result=self.result)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return path


def summarize(check_all, negative=()):
    """Report summary: passed, list of failed checks, number of negative tests caught."""
    return dict(passed=all(c["passed"] for c in check_all),
                failed=[c["id"] + " " + c["name"] for c in check_all if not c["passed"]],
                caught_negatives=sum(n["caught"] for n in negative), negative_count=len(negative))
