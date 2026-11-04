#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Explicit, audited continuation of the original v4.1 allocation experiment.

Python >=3.9. Uses the original run's HASH-VERIFIED code snapshots; this file
can live anywhere. No edits to the original experiment files are needed.

    python resume_experiment.py --run-dir "D:\\...\\formal\\RUN_ID" --preview
    python resume_experiment.py --run-dir "D:\\...\\formal\\RUN_ID"

The API key is read from AZURE_OPENAI_API_KEY (or OPENAI_API_KEY for a saved
OpenAI run). Endpoint, model, prompts, order, retries, token budget and other
parameters come from the saved run. No completed choice, including an invalid
choice, is resubmitted. The factual histories are reconstructed exactly.

Original files remain unchanged. A sibling continuation directory contains
copies of all original evidence plus new attempts and choices. A small sibling
pointer file prevents accidentally starting duplicate continuations from the
same checkpoint. Reusing the same command follows that pointer to the latest
checkpoint; an active run or ambiguous in-flight request is never replayed.

Only --preview is a read-only/no-network action. Without --preview this script
executes the REMAINING paid API requests under the original fixed schedule.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.dont_write_bytecode = True
VERSION = "explicit-continuation-1.0-20261024"


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def iter_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid JSON in {Path(path).name}, line {number}; no automatic repair/replay") from None


def pointer_path(source):
    return source.with_name(source.name + ".continuation_pointer.json")


def follow_chain(source):
    source = Path(source).expanduser().resolve()
    seen = set()
    while True:
        if source in seen:
            raise ValueError("Continuation chain contains a cycle")
        seen.add(source)
        pointer = pointer_path(source)
        if not pointer.exists():
            return source
        target = Path(load_json(pointer)["continuation_directory"]).resolve()
        if not target.is_dir():
            raise ValueError(f"Continuation was reserved but is not ready: {target}; do not start a second run")
        source = target


def load_snapshots(source):
    hashes = load_json(source/"source_hashes.json")
    names = ["experiment_core", "run_experiment"]
    modules = []
    for name in names:
        path = source/("code_snapshot_" + name + ".py")
        if file_sha(path) != hashes[name+".py"]:
            raise ValueError(f"Original code snapshot hash mismatch: {path.name}")
        # Preserve the imported name required by the original history script.
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0], modules[1]


class QuietArchive:
    def append(self, *args):
        pass
    def write_json(self, *args):
        pass


class SavedChoices:
    def __init__(self, saved):
        self.saved = saved
        self.position = 0

    def request(self, messages, context):
        if self.position >= len(self.saved):
            raise ValueError("Checkpoint validation attempted an unsaved request")
        row = self.saved[self.position]
        if (row["trial_id"] != context["trial_id"] or
                row["schedule_index"] != context["schedule_index"] or
                row["messages_sent"] != messages):
            raise ValueError(f"Saved history/input does not match original schedule at {context['trial_id']}")
        self.position += 1
        return dict(row)


def validate(source):
    """Read-only: verify snapshots, plan, all saved choices and audit linkage."""
    source = Path(source).resolve()
    state = load_json(source/"run_status.json")
    if state["state"] == "running":
        raise ValueError("This continuation is marked running; do not launch a second process")
    if state["state"] not in ("interrupted", "failed", "completed", "stopped_configuration_error"):
        raise ValueError("Unsupported checkpoint state: " + str(state["state"]))
    n, h = load_snapshots(source)
    cfg = load_json(source/"config.json")
    plan = load_json(source/"design_manifest.json")
    saved = list(iter_jsonl(source/"decisions.jsonl"))
    if len(saved) > len(plan["events"]):
        raise ValueError("More choices than scheduled events")
    if h.nh.sha256(plan) != cfg["design_sha256"]:
        raise ValueError("Saved design hash mismatch")
    if n.sha256(h.prompt_templates()) != cfg["template_sha256"]:
        raise ValueError("Saved prompt template hash mismatch")
    if n.sha256(load_json(source/"prompts_en_v4_1.json")) != cfg["template_sha256"]:
        raise ValueError("Saved prompt JSON hash mismatch")
    required_params = {"temperature": 0.0, "top_p": 1.0, "max_extra_transport_retries": 2,
                       "concurrency": 1, "store": False, "history_truncation": False}
    for key, value in required_params.items():
        if cfg.get(key) != value:
            raise ValueError("Unexpected frozen configuration: " + key)
    known_attempts = {}
    for i, row in enumerate(saved):
        event = plan["events"][i]
        if any(row.get(k) != v for k, v in event.items()):
            raise ValueError(f"Choices are not an exact contiguous schedule prefix at row {i+1}")
        for attempt in row["attempt_ids"]:
            if attempt in known_attempts:
                raise ValueError("Duplicate attempt association")
            known_attempts[attempt] = row
    seen = set()
    models = set()
    call_count = 0
    for call in iter_jsonl(source/"calls.jsonl"):
        call_count += 1
        aid = call["attempt_id"]
        if aid in seen or aid not in known_attempts:
            raise ValueError("Duplicate or unresolved attempt exists; do not automatically replay its trial")
        seen.add(aid)
        row = known_attempts[aid]
        payload = call["request_json"]
        if (payload.get("messages") != row["messages_sent"] or
                n.sha256(payload) != call["request_sha256"]):
            raise ValueError("Actual request or hash does not match saved choice")
        if call["trial"]["trial_id"] != row["trial_id"]:
            raise ValueError("Attempt belongs to a different trial")
        if payload.get("model") != cfg["model"] or payload.get("temperature") != 0 or payload.get("max_tokens") != cfg["max_output_tokens"]:
            raise ValueError("Actual submitted generation parameters changed")
        if aid == row["final_attempt_id"]:
            if call["parsed"]["choice"] != row["choice"] or call["parsed"]["status"] != row["status"]:
                raise ValueError("Accepted response does not match saved outcome")
            if call.get("http_status") == 200 and call.get("response_model"):
                models.add(call["response_model"])
    if seen != set(known_attempts):
        raise ValueError("An accepted attempt is missing from the call archive")
    started = {r["attempt_id"] for r in iter_jsonl(source/"request_events.jsonl") if r.get("event") == "started"}
    if started != seen:
        raise ValueError("An in-flight/unknown request exists; it must be audited rather than silently retried")
    # Replay LOCAL saved records only. This is not an API call and cannot change
    # any previous choice. The exact original renderer reconstructs all histories.
    short_plan = dict(plan, events=plan["events"][:len(saved)])
    replay_cfg = dict(cfg, pause_sec=0)
    replay, replay_state = h.execute(short_plan, replay_cfg, QuietArchive(), SavedChoices(saved), progress=False)
    if replay_state != "completed" or replay != saved:
        raise ValueError("Exact reconstruction of saved path state failed")
    report = {"source_directory": str(source), "run_id": cfg["run_id"],
              "completed_decisions": len(saved), "planned_decisions": plan["planned_total"],
              "remaining_decisions": len(plan["events"])-len(saved),
              "saved_status_counts": dict(Counter(r["status"] for r in saved)),
              "previous_attempt_count": call_count, "observed_response_models": sorted(models),
              "next_trial": plan["events"][len(saved)] if len(saved)<len(plan["events"]) else None,
              "original_run_state": state, "checkpoint_verified": True}
    return n, h, cfg, plan, saved, report


def copy_evidence(source, dest):
    """Copy to a NEW sibling only, never move/delete/edit original evidence."""
    source = Path(source).resolve()
    dest = Path(dest).resolve()
    if source == dest or source in dest.parents:
        raise ValueError("Continuation must be a new sibling, not inside the source")
    dest.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for file in sorted(source.iterdir()):
        if file.is_symlink() or not file.is_file():
            raise ValueError("Unexpected non-file in evidence directory; refusing implicit recursion")
        before = file_sha(file)
        shutil.copy2(file, dest/file.name)
        if before != file_sha(dest/file.name) or before != file_sha(file):
            raise ValueError("Source changed while being copied")
        hashes[file.name] = before
    return hashes


def continue_run(source, api_key, *, client_factory=None, progress=True, do_analysis=True):
    source = follow_chain(source)
    n, h, cfg, plan, saved, report = validate(source)
    if not report["remaining_decisions"]:
        if progress:
            print("All planned choices are already saved. No API requests sent.")
        return source, "completed", saved
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    cid = timestamp + "_" + uuid.uuid4().hex[:6]
    dest = source.parent / (cfg["run_id"] + "_resume_" + cid)
    pointer = pointer_path(source)
    # Exclusive reservation prevents two shells from resuming the same source.
    with pointer.open("x", encoding="utf-8") as f:
        json.dump({"continuation_directory": str(dest), "source_directory": str(source),
                   "created_utc": n.utc_now(), "continuation_id": cid}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    hashes = copy_evidence(source, dest)

    class ReplayAwareArchive(n.Archive):
        def __init__(self):
            self.directory = dest
            self.secret = api_key

        def append(self, name, value):
            # The copied evidence already contains all prefix decisions. Original
            # execute() replays them locally to restore state; never append twice.
            if name in ("decisions.jsonl", "seed_decisions.jsonl", "H0_formal.jsonl", "H1_formal.jsonl"):
                if value["schedule_index"] <= len(saved):
                    return
            super().append(name, value)

    archive = ReplayAwareArchive()
    runner_copy = "continuation_runner_" + cid + ".py"
    shutil.copy2(Path(__file__).resolve(), dest/runner_copy)
    manifest = {"version": VERSION, "continuation_id": cid, "started_utc": n.utc_now(),
                "source_directory": str(source), "destination_directory": str(dest),
                "source_file_sha256": hashes, "runner_sha256": file_sha(dest/runner_copy),
                "original_config_unchanged": True, "original_evidence_untouched": True,
                "old_failures_retained_without_refill": True, "saved_prefix": report,
                "note": "Technical interruption and continuation; preserved schedule and exact factual histories; no original choices rerun"}
    old_end = report["original_run_state"].get("ended_utc")
    manifest["pause_seconds_since_prior_stop"] = (
        (datetime.fromisoformat(manifest["started_utc"])-datetime.fromisoformat(old_end)).total_seconds()
        if old_end else None)
    archive.write_json("continuation_manifest_" + cid + ".json", manifest)
    archive.write_json("run_status.json", {"state": "running", "started_utc": n.utc_now(),
                                           "completed_decisions": len(saved), "planned_decisions": plan["planned_total"],
                                           "continuation_id": cid, "pid": os.getpid()})
    original_client = (client_factory or n.ChatClient)(cfg, api_key, archive)
    known_models = set(report["observed_response_models"])

    class ResumeClient(SavedChoices):
        def request(self, messages, context):
            if self.position < len(self.saved):
                return super().request(messages, context)
            # Original execute() now uses pause_sec=0 only to avoid sleeping on
            # already-completed local replay. Apply the original pause before
            # each new call instead, with the original transport retries intact.
            if cfg.get("pause_sec", 0):
                time.sleep(cfg["pause_sec"])
            context = dict(context, continuation_id=cid)
            response = original_client.request(messages, context)
            model = response.get("response_model")
            if model and known_models and model not in known_models:
                # Save this outcome and its raw attempt before stopping. Do not
                # silently discard it, switch models, or start another trial.
                response = dict(response, fatal_configuration_error=True,
                                continuation_stop_reason="returned_model_changed")
            if progress:
                print(f"{context['schedule_index']}/{plan['planned_total']} {context['stage']} "
                      f"H={context['H']} D={context['D']} delta={context['Delta']} r={context['r']} "
                      f"t={context['t']} gap={context['g']} "
                      f"history={context['t'] if context['stage']=='formal' and context['H']==1 else 0} "
                      f"{response['status']} choice={response.get('choice') or '-'}", flush=True)
            return dict(response, continuation_id=cid)

    if progress:
        print(f"Verified {len(saved)} saved choices; {report['remaining_decisions']} remaining.", flush=True)
        print("Original evidence preserved. Continuation output: " + str(dest), flush=True)
        print("Restoring exact path histories locally (no paid calls for the saved prefix)...", flush=True)
    execution_cfg = dict(cfg, pause_sec=0)
    rows, state = h.execute(plan, execution_cfg, archive, ResumeClient(saved), progress=False)
    if rows[:len(saved)] != saved:
        raise ValueError("Unexpected prefix reconstruction change; stop and retain evidence")
    status = load_json(dest/"run_status.json")
    status.update(continuation_id=cid, source_directory=str(source),
                  inherited_decisions=len(saved), new_decisions=len(rows)-len(saved))
    archive.write_json("run_status.json", status)
    pathrows = h.write_descriptive_outputs(plan, rows, archive)
    if do_analysis and state == "completed" and plan["phase"] == "formal":
        if progress:
            print("All choices saved. Computing the original paired r-block analysis...", flush=True)
        h.write_paired_analysis(plan, rows, pathrows, archive, cfg)
    if progress:
        print(f"Finished: {state}. Recorded {len(rows)}/{plan['planned_total']}. Saved to {dest}", flush=True)
        if state != "completed":
            print("After resolving the interruption, the SAME command follows the continuation pointer to this latest checkpoint.")
    return dest, state, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", required=True, type=Path, help="Original interrupted run directory")
    parser.add_argument("--preview", action="store_true", help="Validate and report only; no writes or API calls")
    args = parser.parse_args(argv)
    source = follow_chain(args.run_dir)
    if args.preview:
        *_, report = validate(source)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("PREVIEW ONLY: no API calls, no files changed.")
        return 0
    cfg = load_json(source/"config.json")
    env_name = "AZURE_OPENAI_API_KEY" if cfg["api_type"] == "azure" else "OPENAI_API_KEY"
    api_key = os.getenv(env_name, "")
    if not api_key:
        raise SystemExit(f"Set {env_name} in this PowerShell window. No original data changed or calls made.")
    try:
        import requests  # original dependency, no OpenAI SDK/hidden retry layer
    except ImportError:
        raise SystemExit("Use the original Python environment, or install requests first.")
    _, state, _ = continue_run(source, api_key)
    return 0 if state == "completed" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileExistsError) as exc:
        raise SystemExit("Continuation not started/completed: " + str(exc)) from None
