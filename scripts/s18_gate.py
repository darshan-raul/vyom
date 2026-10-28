"""Helpers for scripts/s18-gate.sh: parse and check telemetry. Reads files, prints facts only.

Subcommands (each prints one line or exits non-zero with a reason):
  loki-summary FILE          logger counts and duplicate (timestamp, line) pairs in a Loki result
  trace-summary FILE         span names, whether the tree is connected, duplicate span IDs
  trace-grep FILE NEEDLE..   exit 1 if any needle appears anywhere in the trace JSON
  loki-grep FILE             exit 1 if the result holds any line (used with a needle query)
  derived FILE REGEX         the trace ID a Grafana derived-field regex extracts from a Loki line
  dump-summary FILE          lines, exact duplicate lines, repeated (trace, span, logger) records
  scan KEYFILE NEEDLE... -- FILE...
                             count files containing each needle or the key in KEYFILE; prints
                             needle names and hit counts, never the key
"""

import collections
import json
import re
import sys


def spans(path):
    data = json.load(open(path))
    return [s for b in data.get("batches", []) for ss in b["scopeSpans"] for s in ss["spans"]]


def loki_lines(path):
    data = json.load(open(path))
    return [(t, line) for r in data["data"]["result"] for t, line in r["values"]]


def main(argv):
    cmd = argv[1]
    if cmd == "loki-summary":
        lines = loki_lines(argv[2])
        loggers = collections.Counter(json.loads(line).get("logger") for _, line in lines)
        duplicates = len(lines) - len(set(lines))
        print(json.dumps({"lines": len(lines), "loggers": dict(loggers), "duplicates": duplicates}))
    elif cmd == "trace-summary":
        items = spans(argv[2])
        ids = [s["spanId"] for s in items]
        known = set(ids)
        roots = [s for s in items if not s.get("parentSpanId")]
        orphans = [s["name"] for s in items if s.get("parentSpanId") and s["parentSpanId"] not in known]
        print(
            json.dumps(
                {
                    "spans": len(items),
                    "names": sorted({s["name"] for s in items}),
                    "roots": len(roots),
                    "orphans": orphans,
                    "duplicate_span_ids": len(ids) - len(known),
                }
            )
        )
    elif cmd == "trace-grep":
        text = open(argv[2]).read()
        hits = [needle for needle in argv[3:] if needle in text]
        print(json.dumps({"hits": hits}))
        return 1 if hits else 0
    elif cmd == "loki-grep":
        lines = loki_lines(argv[2])
        print(json.dumps({"lines": len(lines)}))
        return 1 if lines else 0
    elif cmd == "derived":
        line = loki_lines(argv[2])[0][1]
        match = re.search(argv[3], line)
        print(match.group(1) if match else "")
    elif cmd == "dump-summary":
        lines = loki_lines(argv[2])
        records = collections.Counter()
        for _, line in lines:
            try:
                body = json.loads(line)
            except ValueError:
                continue
            if body.get("trace_id"):
                records[(body["trace_id"], body.get("span_id"), body.get("logger"), body.get("message"))] += 1
        repeated = sum(count - 1 for count in records.values() if count > 1)
        print(json.dumps({"lines": len(lines), "exact_duplicate_lines": len(lines) - len(set(lines)),
                          "repeated_records": repeated, "traces": len({r[0] for r in records})}))
        return 1 if len(lines) != len(set(lines)) or repeated else 0
    elif cmd == "scan":
        split = argv.index("--")
        key = open(argv[2]).read().strip()
        needles = {n: n for n in argv[3:split]}
        needles["<model key>"] = key
        hits = {}
        for path in argv[split + 1 :]:
            text = open(path, errors="replace").read()
            for name, needle in needles.items():
                if needle and needle in text:
                    hits[name] = hits.get(name, 0) + 1
        print(json.dumps({"files": len(argv) - split - 1, "hits": hits}))
        return 1 if hits else 0
    else:
        print(__doc__)
        return 2
    return 0


sys.exit(main(sys.argv))
