"""
Shared runner plumbing for every slice: the CLI surface, the default report, and durable
results-writing. Extracted because it was near-identical seven times; the parts that make a
slice a slice — run_replay / run_live / (occasionally) a custom report — stay in the slice,
so each remains readable standalone.

What lives here:
  - build_parser / main: the standard flags (--replay/--live/--model/--samples/--out/
    --instances) plus the run-pinning ones (--temperature, --base-url). --base-url exports
    $OPENAI_BASE_URL so one mechanism reaches both call paths (providers.call_model and
    harness.run_trajectory).
  - report: the default per-item + aggregate printout. A slice with a genuinely different
    read (mode 8's Gate-2 mix-check) passes its own report_fn.
  - ResultSink / write_results: LIVE-RUN DURABILITY. The sink rewrites --out (atomically:
    tmp + os.replace) after EVERY completed record, marked "partial": true — an aborted run
    preserves every sample already paid for, where previously a crash at sample 29/30
    discarded all 30. The final write carries the summary and "partial": false. Sampling
    params are recorded inside the file: a results file that can't state the params it ran
    with isn't reproducible.

The contract a slice's run_live must satisfy:
    run_live(instances_path, model, samples, temperature=..., on_record=None) -> list[dict]
calling on_record(rec) after each completed record (that is the sink's flush hook).
ProviderError from the run is caught here: the partial file survives, the exit is clean.
"""

import argparse
import datetime
import json
import os
import sys

from providers import DEFAULT_TEMPERATURE, ProviderError


def build_parser(description: str, here: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--instances", default=os.path.join(here, "instances.yaml"))
    ap.add_argument("--replay", help="fixtures-style yaml of recorded responses (offline)")
    ap.add_argument("--live", action="store_true",
                    help="call a model (needs a provider key: ANTHROPIC_API_KEY / MISTRAL_API_KEY / "
                         "OPENAI_API_KEY — or --base-url for any OpenAI-compatible endpoint)")
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", ""),
                    help="model id (live) / results label")
    ap.add_argument("--samples", type=int, default=1,
                    help="samples per instance (live; stochasticity)")
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                    help=f"sampling temperature, recorded in results (default {DEFAULT_TEMPERATURE})")
    ap.add_argument("--base-url", default=None,
                    help="OpenAI-compatible endpoint (Ollama/vLLM/Groq/...); also via $OPENAI_BASE_URL")
    ap.add_argument("--out", help="write results json here (live: flushed after every record)")
    return ap


def report(results: list[dict], model_label: str, id_width: int = 16) -> dict:
    """Default per-item + aggregate printout; returns the summary block for the results file."""
    counts = {"pass": 0, "fail": 0, "uncertain": 0}
    for r in results:
        counts[r["verdict"]] += 1
    decided = counts["pass"] + counts["fail"]
    pass_rate = (counts["pass"] / decided) if decided else None

    print(f"model: {model_label}")
    print(f"items graded: {len(results)}\n")
    for r in results:
        agree = ""
        if "grader_agrees" in r:
            agree = "  [label match]" if r["grader_agrees"] else f"  [LABEL MISMATCH expect={r['expect']}]"
        print(f"  {r['id']:<{id_width}} {r['verdict']:<10} {r['reason']}{agree}")

    print(f"\naggregate: pass={counts['pass']}  fail={counts['fail']}  uncertain={counts['uncertain']}")
    print(
        "pass-rate over decided cases: "
        + (f"{pass_rate:.0%}  ({counts['pass']}/{decided})" if decided else "n/a")
    )
    uncertain = [r["id"] for r in results if r["verdict"] == "uncertain"]
    if uncertain:
        print(f"uncertain → route to human / LLM-judge: {uncertain}")
    labelled = [r for r in results if "grader_agrees" in r]
    if labelled:
        agreed = sum(1 for r in labelled if r["grader_agrees"])
        print(f"grader vs fixture labels: {agreed}/{len(labelled)} agree")
    return {"counts": counts, "pass_rate_decided": pass_rate}


def _record(model_label, mode_name, params, summary, results, partial):
    rec = {
        "model": model_label,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": mode_name,
    }
    if params:
        rec["params"] = params
    if summary:
        rec.update(summary)
    rec["partial"] = partial
    rec["results"] = results
    return rec


def _atomic_write(path, rec):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class ResultSink:
    """Rewrites the output file after every added record — always-valid JSON on disk, so a
    crash mid-run loses at most the in-flight call."""

    def __init__(self, path, model_label, mode_name, params):
        # Rerun insurance: never destroy an existing results file — snapshot it once before the
        # first flush overwrites it (a partial rerun once clobbered a larger partial: 18->11
        # records lost, 2026-07-02). The .prev is untracked working data.
        if os.path.exists(path):
            os.replace(path, path + ".prev")
        self.path = path
        self.model_label = model_label
        self.mode_name = mode_name
        self.params = params
        self.records = []

    def add(self, rec):
        self.records.append(rec)
        _atomic_write(self.path, _record(self.model_label, self.mode_name, self.params,
                                         None, self.records, partial=True))


def write_results(path, model_label, mode_name, summary, results, params=None):
    _atomic_write(path, _record(model_label, mode_name, params, summary, results, partial=False))


def main(description: str, mode_name: str, here: str, run_replay, run_live,
         report_fn=None, replay_label: str = "replay (synthetic fixtures)", argv=None) -> None:
    """Standard slice-runner entry point. The slice supplies run_replay / run_live (and
    optionally a custom report); flags, durability, and the results record are shared."""
    report_fn = report_fn or report
    ap = build_parser(description, here)
    args = ap.parse_args(argv)

    if not args.replay and not args.live:
        ap.error("choose --replay FILE or --live")
    if args.base_url:
        # One mechanism for both call paths: providers.call_model and harness.run_trajectory
        # read $OPENAI_BASE_URL.
        os.environ["OPENAI_BASE_URL"] = args.base_url

    params = None
    if args.replay:
        results = run_replay(args.replay)
        model_label = args.model or replay_label
    else:
        if not args.model:
            ap.error("--live needs --model <model-id> (or EVAL_MODEL)")
        model_label = args.model
        params = {"temperature": args.temperature, "samples": args.samples,
                  "base_url": args.base_url or os.environ.get("OPENAI_BASE_URL")}
        sink = ResultSink(args.out, model_label, mode_name, params) if args.out else None
        try:
            results = run_live(args.instances, args.model, args.samples,
                               temperature=args.temperature,
                               on_record=sink.add if sink else None)
        except ProviderError as e:
            print(f"\n[runlib] live run aborted: {e}", file=sys.stderr)
            if sink and sink.records:
                print(f"[runlib] {len(sink.records)} completed record(s) preserved in "
                      f"{args.out} (partial: true)", file=sys.stderr)
            sys.exit(1)

    summary = report_fn(results, model_label)

    if args.out:
        write_results(args.out, model_label, mode_name, summary, results, params)
        print(f"\nwrote {args.out}")

    # Replay of a labelled file is a regression check: any grader-vs-label disagreement is a
    # nonzero exit, so `run.py` / CI can catch grader drift through the real runner path.
    if args.replay and any(r.get("grader_agrees") is False for r in results):
        sys.exit(1)
