#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF v4.1 paired experiment: H=1 histories and the joint H0/H1 runner.

Place beside experiment_core.py. Do not launch both scripts.
Run this one entry point to collect BOTH conditions with randomized order.
Python >=3.9; pip install requests. See --help and --preview before running.

FORMAL: 50 paths per (Delta,D), one seed + 10 formal pairs per path.
PILOT: 2 paths per (Delta,D), Delta in {1,4.9,5}; never pooled with formal.
No original files are read, imported, overwritten or needed at runtime.
Only the pre-specified factual history crosses projects within an H1 path.

Analysis outputs are numerical tables, not manuscript figures. Optional
regressions and power claims are not manufactured. Bootstrap resamples the
entire r block jointly across all Delta, D, H, and g. The two-sided primary
test uses paired block sign flips, with Holm correction across the two D's.
This test implementation is explicit because the PDF does not select a
particular two-sided test. Identical outputs do not establish population
invariance; 50 paths are not 50 independent model personalities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time
import uuid

import experiment_core as nh

# PDF 6.4--6.7, with print line wrapping/quotation glyphs normalized only.
HISTORY_TEMPLATE = """[Records of your earlier project decisions]

The projects listed below have ended. Each involved a different colleague, none of whom is your colleague in the current project. In every project, you and that colleague completed the same work and had the same eligibility for compensation.

All amounts are expressed in units of RMB 10,000.

Decision counts across these records: Option A selected: {countA} Option B selected: {countB}
No valid selection recorded: {countInvalid}

Decision counts by the payment gap in Option B: The payment gap is the colleague's payment minus your payment.
{gapCountRows}

Project records, in chronological order:
{projectRecordRows}

These records describe earlier projects. The current project's compensation options are presented below."""
GAP_TEMPLATE = "Gap {gap}: {countTotal} project(s); Option A selected {countA} time(s); Option B selected {countB} time(s); no valid selection {countInvalid} time(s)."
RECORD_PREFIX = "Project {projectNumber} Option A offered: 5 to you; 5 to that project's colleague. Option B offered: {ownPay} to you; {colleaguePay} to that project's colleague."
VALID_TEMPLATE = RECORD_PREFIX + " Your selection: {selectedOption}. Recorded payments: {paidOwn} to you; {paidColleague} to that project's colleague."
INVALID_TEMPLATE = RECORD_PREFIX + " No valid selection was recorded. No payment was settled for this project."


def prompt_templates():
    return {"system": nh.SYSTEM_PROMPT, "current_prefix": nh.CURRENT_PREFIX,
            "blind_options": nh.BLIND_OPTIONS, "disclosed_options": nh.DISCLOSED_OPTIONS,
            "disclosure": nh.DISCLOSURE, "current_suffix": nh.CURRENT_SUFFIX,
            "history": HISTORY_TEMPLATE, "gap_count": GAP_TEMPLATE,
            "valid_history_record": VALID_TEMPLATE, "invalid_history_record": INVALID_TEMPLATE}


def history_counts(records):
    counts = Counter({"A": 0, "B": 0, "invalid": 0})
    for rec in records:
        counts[rec["choice"] if rec["choice"] in ("A", "B") else "invalid"] += 1
    return dict(counts)


def render_history(records):
    if not 1 <= len(records) <= 10:
        raise ValueError("Each formal H1 input must contain 1--10 complete factual records")
    # Every record is an immutable seed/H1 result from THIS path, in time order.
    path = records[0]["path_id"]
    for i, rec in enumerate(records):
        if rec["path_id"] != path or rec["H"] != 1 or rec["t"] != i:
            raise ValueError("History contains a foreign path, H0 result, or wrong chronology")
    counts = history_counts(records)
    gap_rows = []
    for gap in nh.GAPS:  # always all ten original gaps, including zero-count gaps
        selected = [r for r in records if r["g"] == gap]
        c = history_counts(selected)
        gap_rows.append(GAP_TEMPLATE.format(gap=gap, countTotal=len(selected),
                                           countA=c["A"], countB=c["B"], countInvalid=c["invalid"]))
    project_rows = []
    for i, rec in enumerate(records, 1):
        pay = nh.amounts(rec["Delta"], rec["g"])
        values = {"projectNumber": i, "ownPay": pay["B_you"], "colleaguePay": pay["B_colleague"]}
        if rec["choice"] in ("A", "B"):
            values.update(selectedOption="Option " + rec["choice"],
                          paidOwn=pay[rec["choice"] + "_you"],
                          paidColleague=pay[rec["choice"] + "_colleague"])
            project_rows.append(VALID_TEMPLATE.format(**values))
        else:
            project_rows.append(INVALID_TEMPLATE.format(**values))
    return HISTORY_TEMPLATE.format(countA=counts["A"], countB=counts["B"],
                                   countInvalid=counts["invalid"], gapCountRows="\n".join(gap_rows),
                                   projectRecordRows="\n".join(project_rows))


def build_messages(delta, gap, D, history):
    base = nh.build_messages(delta, gap, D)
    block = render_history(history)
    return [base[0], {"role": "user", "content": block + "\n\n" + base[1]["content"]}]


def build_plan(phase="formal", seed=41, framing="both"):
    """Freeze all schedules before seeing outputs; results never change order."""
    R = 50 if phase == "formal" else 2
    deltas = nh.DELTAS if phase == "formal" else nh.PILOT_DELTAS
    Ds = (0, 1) if framing == "both" else (0,)
    rng = random.Random(f"{nh.PROTOCOL_VERSION}|{phase}|{seed}|design")
    seed_gaps = list(nh.GAPS) * (R // 10)
    if R % 10:
        seed_gaps += rng.sample(list(nh.GAPS), R % 10)
    rng.shuffle(seed_gaps)
    shared = {}
    for r in range(1, R + 1):
        order = list(nh.GAPS)
        rng.shuffle(order)
        shared[r] = {"g_order": order, "seed_g": seed_gaps[r-1]}
    paths = []
    for delta in deltas:
        for D in Ds:
            for r in range(1, R + 1):
                paths.append({"path_id": f"r{r:02d}_delta{delta}_D{D}", "r": r,
                              "Delta": delta, "D": D, **shared[r]})
    # Cross-path interleaving: all paths advance by one formal position per sweep.
    # The two H requests for each current project are adjacent in a random order.
    events = []
    shuffled = list(paths)
    rng.shuffle(shuffled)
    for path in shuffled:
        events.append({**path, "H": 1, "t": 0, "g": path["seed_g"], "stage": "seed",
                       "pair_id": None, "pair_order": None, "pair_slot": None})
    for t in range(1, 11):
        shuffled = list(paths)
        rng.shuffle(shuffled)
        for path in shuffled:
            order = [0, 1]
            rng.shuffle(order)
            pair_id = path["path_id"] + f"_t{t:02d}"
            for slot, H in enumerate(order, 1):
                events.append({**path, "H": H, "t": t, "g": path["g_order"][t-1],
                               "stage": "formal", "pair_id": pair_id,
                               "pair_order": order, "pair_slot": slot})
    for index, event in enumerate(events, 1):
        event["schedule_index"] = index
        event["trial_id"] = f"{phase}_{event['path_id']}_{event['stage']}_t{event['t']:02d}_H{event['H']}"
    plan = {"protocol_version": nh.PROTOCOL_VERSION, "phase": phase, "random_seed": seed,
            "R": R, "deltas": list(deltas), "gaps": list(nh.GAPS), "Ds": list(Ds),
            "paths": paths, "events": events,
            "planned_formal_per_H": len(deltas)*len(Ds)*R*10,
            "planned_seed": len(paths), "planned_total": len(events)}
    validate_plan(plan)
    return plan


def validate_plan(plan):
    R = plan["R"]
    formal = [e for e in plan["events"] if e["stage"] == "formal"]
    cells = Counter((e["H"], e["D"], e["Delta"], e["g"]) for e in formal)
    assert len(cells) == 2*len(plan["Ds"])*len(plan["deltas"])*10
    assert set(cells.values()) == {R}
    assert len({e["trial_id"] for e in plan["events"]}) == plan["planned_total"]
    for r in range(1, R+1):
        paths = [p for p in plan["paths"] if p["r"] == r]
        assert len({tuple(p["g_order"]) for p in paths}) == 1
        assert len({p["seed_g"] for p in paths}) == 1
        assert set(paths[0]["g_order"]) == set(nh.GAPS)
    if plan["phase"] == "formal":
        one_per_r = {p["r"]: p["seed_g"] for p in plan["paths"]}
        assert set(Counter(one_per_r.values()).values()) == {5}
    for first, second in zip(formal[::2], formal[1::2]):
        assert first["pair_id"] == second["pair_id"] and first["H"] != second["H"]
        assert first["schedule_index"]+1 == second["schedule_index"]


def describe(plan):
    return {k: plan[k] for k in ("protocol_version", "phase", "R", "deltas", "gaps", "Ds",
                                "planned_formal_per_H", "planned_seed", "planned_total")}


def compact_record(row):
    # Only factual choices/amounts feed history, never raw completions or explanations.
    return {k: row[k] for k in ("trial_id", "path_id", "H", "D", "Delta", "g", "t", "stage",
                                "choice", "Y", "status", "paid_you", "paid_colleague")}


def execute(plan, config, archive, client, progress=True):
    histories = {p["path_id"]: [] for p in plan["paths"]}
    rows = []
    state = "running"
    stopped_at = None
    error = None
    try:
        for event in plan["events"]:
            stopped_at = event["trial_id"]
            history = histories[event["path_id"]]
            use_history = event["stage"] == "formal" and event["H"] == 1
            # H0 must not read the growing history even if its paired H1 ran first.
            prior = [dict(x) for x in history] if use_history else []
            if use_history and len(prior) != event["t"]:
                raise AssertionError("Incorrect history length before choice")
            block = render_history(prior) if use_history else ""
            messages = (build_messages(event["Delta"], event["g"], event["D"], prior) if use_history
                        else nh.build_messages(event["Delta"], event["g"], event["D"]))
            context = {"run_id": config["run_id"], "protocol_version": nh.PROTOCOL_VERSION,
                       "model_condition": config["model_condition"], "phase": plan["phase"], **event}
            result = client.request(messages, context)
            pay = nh.amounts(event["Delta"], event["g"])
            choice = result["choice"]
            row = {**context, **result, **pay,
                   "amount_unit": "RMB 10000", "amounts_exact_decimal_text": pay,
                   "paid_you": pay[choice+"_you"] if choice in ("A", "B") else None,
                   "paid_colleague": pay[choice+"_colleague"] if choice in ("A", "B") else None,
                   "valid": choice in ("A", "B"), "parser_version": nh.PARSER_VERSION,
                   "history_records_sent": prior, "history_length": len(prior),
                   "history_counts": history_counts(prior), "history_block_sent": block,
                   "history_sha256": nh.sha256(block), "messages_sent": messages,
                   "messages_sha256": nh.sha256(messages), "prompt_language": "en",
                   "template_sha256": nh.sha256(prompt_templates()),
                   "history_contains_invalid_prior": any(r["choice"] is None for r in prior)}
            archive.append("decisions.jsonl", row)
            archive.append("seed_decisions.jsonl" if event["stage"] == "seed" else
                           f"H{event['H']}_formal.jsonl", row)
            rows.append(row)
            if event["H"] == 1:
                history.append(compact_record(row))
            if progress:
                print(f"{event['schedule_index']}/{plan['planned_total']} {event['stage']} "
                      f"H={event['H']} D={event['D']} delta={event['Delta']} r={event['r']} "
                      f"t={event['t']} gap={event['g']} history={len(prior)} "
                      f"{result['status']} choice={choice or '-'}", flush=True)
            if result.get("fatal_configuration_error"):
                state = "stopped_configuration_error"
                break
            if config.get("pause_sec", 0):
                time.sleep(config["pause_sec"])
        else:
            state = "completed"
            stopped_at = None
    except KeyboardInterrupt:
        state = "interrupted"
    except Exception as exc:
        state = "failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        # Real completed observations retained; never auto-restart a contaminated path.
        archive.write_json("run_status.json", {"state": state, "ended_utc": nh.utc_now(),
                                               "completed_decisions": len(rows),
                                               "planned_decisions": plan["planned_total"],
                                               "stopped_at_trial": stopped_at, "error": error,
                                               "automatic_resume": False})
    return rows, state


def write_descriptive_outputs(plan, rows, archive):
    formal = [r for r in rows if r["stage"] == "formal"]
    seeds = [r for r in rows if r["stage"] == "seed"]
    groups = defaultdict(list)
    for row in formal:
        groups[(row["H"], row["D"], row["Delta"], row["g"])].append(row)
    cells = []
    p_lookup = {}
    for H in (0, 1):
        for D in plan["Ds"]:
            for delta in plan["deltas"]:
                for gap in plan["gaps"]:
                    group = groups[(H, D, delta, gap)]
                    a = sum(r["choice"] == "A" for r in group)
                    b = sum(r["choice"] == "B" for r in group)
                    p = b/(a+b) if a+b else None
                    p_lookup[(H, D, delta, gap)] = p
                    cells.append({"H": H, "D": D, "Delta": delta, "g": gap,
                                  "planned": plan["R"], "recorded": len(group),
                                  "not_recorded": plan["R"]-len(group), "n_valid": a+b,
                                  "n_A": a, "n_B": b, "n_invalid": len(group)-a-b,
                                  "p_B": p, "p_A": 1-p if p is not None else None,
                                  "invalid_types": dict(Counter(r["status"] for r in group if not r["valid"]))})
    archive.csv("cell_summary.csv", cells)
    fields = ["run_id", "phase", "trial_id", "stage", "path_id", "r", "Delta", "g", "D", "H", "t",
              "seed_g", "schedule_index", "pair_id", "pair_slot", "choice", "Y", "valid", "status",
              "A_you", "A_colleague", "B_you", "B_colleague", "paid_you", "paid_colleague",
              "history_length", "history_contains_invalid_prior", "response_model", "response_id",
              "retry_count", "final_attempt_id"]
    for name, subset in [("H0_formal.csv", [r for r in formal if r["H"] == 0]),
                         ("H1_formal.csv", [r for r in formal if r["H"] == 1]), ("seed_decisions.csv", seeds)]:
        archive.csv(name, [{k: r.get(k) for k in fields} for r in subset], fields)
    pathrows = []
    pathgroups = defaultdict(list)
    for row in rows:
        if row["H"] == 1:
            pathgroups[row["path_id"]].append(row)
    for path in plan["paths"]:
        rr = pathgroups[path["path_id"]]
        invalid = [r["trial_id"] for r in rr if not r["valid"]]
        pathrows.append({**path, "H1_recorded_including_seed": len(rr),
                         "H1_valid_including_seed": sum(r["valid"] for r in rr),
                         "invalid_trial_ids": invalid, "contains_invalid": bool(invalid),
                         "complete_valid_H1_path": len(rr) == 11 and not invalid})
    archive.csv("path_validity.csv", pathrows)
    positions = Counter((p["g_order"][t-1], t) for p in plan["paths"]
                        if p["Delta"] == plan["deltas"][0] and p["D"] == plan["Ds"][0]
                        for t in range(1, 11))
    archive.csv("gap_position_design.csv", [{"g": g, "t": t, "n_paths": positions[(g, t)]}
                                            for g in plan["gaps"] for t in range(1, 11)])
    transitions = []
    for H in (0, 1):
        for D in plan["Ds"]:
            for gap in plan["gaps"]:
                local = []
                probs = [p_lookup[(H, D, d, gap)] for d in plan["deltas"]]
                for j in range(len(plan["deltas"])-1):
                    lo, hi = probs[j:j+2]
                    if lo is None or hi is None:
                        continue  # Never bridge an unobserved grid point.
                    direction = "up" if lo < .5 <= hi else "down" if hi < .5 <= lo else None
                    if direction:
                        local.append({"H": H, "D": D, "g": gap, "direction": direction,
                                      "Delta_lower": plan["deltas"][j], "Delta_upper": plan["deltas"][j+1],
                                      "p_lower": lo, "p_upper": hi, "final_upward": False,
                                      "profile_has_missing_cells": any(p is None for p in probs)})
                ups = [r for r in local if r["direction"] == "up"]
                if ups:
                    ups[-1]["final_upward"] = True
                if not local:
                    local = [{"H": H, "D": D, "g": gap, "direction": "no_localized_crossing",
                              "Delta_lower": None, "Delta_upper": None, "p_lower": None,
                              "p_upper": None, "final_upward": False,
                              "profile_has_missing_cells": any(p is None for p in probs)}]
                transitions.extend(local)
    archive.csv("observed_transition_intervals.csv", transitions)
    archive.write_json("summary.json", {**describe(plan), "recorded_formal": len(formal),
                                       "recorded_seed": len(seeds),
                                       "formal_status_counts": dict(Counter(r["status"] for r in formal)),
                                       "seed_status_counts": dict(Counter(r["status"] for r in seeds)),
                                       "seed_excluded_from_formal_proportions": True,
                                       "invalid_not_replaced_or_imputed_in_proportions": True})
    return pathrows


def quantile(values, q):
    values = sorted(values)
    if not values:
        return None
    loc = (len(values)-1)*q
    lo = math.floor(loc)
    hi = math.ceil(loc)
    return values[lo] + (loc-lo)*(values[hi]-values[lo])


def write_paired_analysis(plan, rows, pathrows, archive, config):
    """Matched contrasts; block bootstrap, not one-bootstrap-unit-per-request."""
    lookup = {(r["r"], r["Delta"], r["g"], r["D"], r["H"]): r["Y"]
              for r in rows if r["stage"] == "formal"}
    validpaths = {p["path_id"] for p in pathrows if p["complete_valid_H1_path"]}
    # All fixed grids are retained even when outcomes are missing.
    blockrows = []
    specs = [("overall", None, None)]
    specs += [("Delta", d, None) for d in plan["deltas"]]
    specs += [("position", None, t) for t in range(1, 11)]
    paths = {(p["r"], p["Delta"], p["D"]): p for p in plan["paths"]}
    for D in plan["Ds"]:
        for stratum, delta_filter, t_filter in specs:
            for r in range(1, plan["R"]+1):
                total = count = diff_sum = 0
                lower = upper = 0
                clean_sum = clean_count = 0
                for delta in plan["deltas"]:
                    if delta_filter is not None and delta != delta_filter:
                        continue
                    path = paths[(r, delta, D)]
                    for t, gap in enumerate(path["g_order"], 1):
                        if t_filter is not None and t != t_filter:
                            continue
                        y0 = lookup.get((r, delta, gap, D, 0))
                        y1 = lookup.get((r, delta, gap, D, 1))
                        total += 1
                        lower += (y1 if y1 is not None else 0) - (y0 if y0 is not None else 1)
                        upper += (y1 if y1 is not None else 1) - (y0 if y0 is not None else 0)
                        if y0 is not None and y1 is not None:
                            diff_sum += y1-y0
                            count += 1
                            if path["path_id"] in validpaths:
                                clean_sum += y1-y0
                                clean_count += 1
                blockrows.append({"D": D, "stratum": stratum, "Delta": delta_filter, "t": t_filter,
                                  "r": r, "planned_pairs": total, "complete_pairs": count,
                                  "difference_sum": diff_sum,
                                  "d_r_complete_pairs": diff_sum/count if count else None,
                                  "lower_sum": lower, "upper_sum": upper,
                                  "clean_H1_path_difference_sum": clean_sum,
                                  "clean_H1_path_complete_pairs": clean_count})
    archive.csv("paired_block_statistics.csv", blockrows)
    # The SAME r draws/signs are used for every D/stratum, preserving dependence.
    rng = random.Random(f"{config['random_seed']}|{plan['phase']}|analysis-v1")
    B = config["bootstrap_replicates"]
    draws = [[rng.randrange(plan["R"]) for _ in range(plan["R"])] for _ in range(B)]
    signs = [[rng.choice((-1, 1)) for _ in range(plan["R"])] for _ in range(B)]
    groups = defaultdict(list)
    for row in blockrows:
        groups[(row["D"], row["stratum"], row["Delta"], row["t"])].append(row)
    effects = []
    for (D, stratum, delta, t), blocks in groups.items():
        blocks.sort(key=lambda x: x["r"])
        denom = sum(b["complete_pairs"] for b in blocks)
        numerator = sum(b["difference_sum"] for b in blocks)
        total = sum(b["planned_pairs"] for b in blocks)
        estimate = numerator/denom if denom else None
        boot = []
        cleanboot = []
        for draw in draws:
            n = sum(blocks[i]["complete_pairs"] for i in draw)
            if n:
                boot.append(sum(blocks[i]["difference_sum"] for i in draw)/n)
            cn = sum(blocks[i]["clean_H1_path_complete_pairs"] for i in draw)
            if cn:
                cleanboot.append(sum(blocks[i]["clean_H1_path_difference_sum"] for i in draw)/cn)
        p = None
        if denom and stratum == "overall":
            extreme = sum(abs(sum(s*b["difference_sum"] for s, b in zip(ss, blocks))) >= abs(numerator)
                          for ss in signs)
            p = (extreme+1)/(B+1)
        clean_n = sum(b["clean_H1_path_complete_pairs"] for b in blocks)
        effects.append({"D": D, "stratum": stratum, "Delta": delta, "t": t,
                        "planned_pairs": total, "complete_pairs": denom,
                        "tau_H_complete_pairs": estimate,
                        "ci95_low": quantile(boot, .025), "ci95_high": quantile(boot, .975),
                        "full_grid_missing_lower": sum(b["lower_sum"] for b in blocks)/total,
                        "full_grid_missing_upper": sum(b["upper_sum"] for b in blocks)/total,
                        "clean_H1_path_complete_pairs": clean_n,
                        "clean_H1_path_tau_H": sum(b["clean_H1_path_difference_sum"] for b in blocks)/clean_n if clean_n else None,
                        "clean_H1_path_ci95_low": quantile(cleanboot, .025),
                        "clean_H1_path_ci95_high": quantile(cleanboot, .975),
                        "p_two_sided_block_sign_flip": p, "p_Holm_primary": None,
                        "bootstrap_valid_replicates": len(boot)})
    primary = [x for x in effects if x["stratum"] == "overall"]
    # Only run the primary tests when both primary estimates are available.
    if all(x["p_two_sided_block_sign_flip"] is not None for x in primary):
        ordered = sorted(primary, key=lambda x: x["p_two_sided_block_sign_flip"])
        previous = 0.0
        for i, row in enumerate(ordered):
            previous = max(previous, min(1.0, (len(ordered)-i)*row["p_two_sided_block_sign_flip"]))
            row["p_Holm_primary"] = previous
    archive.csv("paired_history_effects.csv", effects)
    archive.write_json("analysis_methods.json", {
        "resampling_unit": "r block, jointly across all Delta, D, H and g",
        "replicates": B, "CI": "percentile block bootstrap, 2.5% and 97.5%",
        "primary_test": "two-sided paired r-block sign-flip Monte Carlo, add-one p-value; Holm across D",
        "test_assumption": "paired block differences exchangeable under sign reversal under the null",
        "test_selection": "implementation choice: PDF specifies two-sided tests but not a particular test",
        "missing": "complete-pair conditional estimates AND worst-case 0/1 bounds on the full planned grid",
        "clean_path_sensitivity": "require every seed and H1 formal record valid in that (r,Delta,D) path",
        "pilot": plan["phase"] == "pilot",
        "inference_scope": "this endpoint/configuration/short-history protocol; paths are not model personalities",
        "secondary_strata": "original ten Delta levels and formal positions t; no data-selected strata",
        "not_produced": "manuscript figures and optional regression models"})


def get_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=("pilot", "formal"), default="pilot",
                    help="Default pilot: 252 requests. Formal: 21,000 requests (both D).")
    ap.add_argument("--preview", action="store_true", help="Print design and prompts; no API calls or output files")
    ap.add_argument("--framing", choices=("both", "blind"), default="both",
                    help="Freeze before running. Blind-only variant loses the framing contrast.")
    ap.add_argument("--api-type", choices=("azure", "openai"), default="azure")
    ap.add_argument("--endpoint", "--api_url", default=None)
    ap.add_argument("--model", default=None, help="Azure deployment NAME or OpenAI-compatible model identifier")
    ap.add_argument("--model-condition", default=None, help="Explicit name for this new endpoint/model/configuration")
    ap.add_argument("--seed", type=int, default=41, help="Local design seed; NOT an API sampling seed")
    ap.add_argument("--max-output-tokens", type=int, default=128, help="Freeze after pilot; same for both H")
    ap.add_argument("--timeout-sec", "--timeout_sec", type=float, default=120)
    ap.add_argument("--pause-sec", type=float, default=.2)
    ap.add_argument("--output-root", "--output_root", type=Path,
                    default=Path(__file__).resolve().parent / "results_v4_1")
    ap.add_argument("--study-id", default="allocation_history_v4_1")
    ap.add_argument("--bootstrap-replicates", type=int, default=5000)
    ap.add_argument("--minimum-effect", type=float, default=.10,
                    help="Prospective effect of interest (probability points); no claim of achieved power")
    args = ap.parse_args(argv)
    if args.max_output_tokens <= 0 or args.timeout_sec <= 0 or args.pause_sec < 0:
        ap.error("Token limit/timeout must be positive; pause must be nonnegative")
    if args.bootstrap_replicates < 1000 or not 0 < args.minimum_effect <= 1:
        ap.error("Use at least 1000 resamples and a minimum effect in (0,1]")
    return args


def main(argv=None):
    args = get_args(argv)
    plan = build_plan(args.phase, args.seed, args.framing)
    if args.preview:
        print(json.dumps(describe(plan), ensure_ascii=False, indent=2))
        print("\nSHARED SYSTEM\n" + nh.SYSTEM_PROMPT)
        for D in plan["Ds"]:
            print(f"\nCURRENT PROJECT D={D}, Delta=4.9, g=20\n" + nh.current_project("4.9", "20", D))
        print("\nHISTORY TEMPLATE (placeholders only; actual records come from real H1 outcomes)\n" + HISTORY_TEMPLATE)
        print("\nBoth entry points run paired H0+H1. Do not start two concurrent copies.")
        return 0
    env_prefix = "AZURE_OPENAI" if args.api_type == "azure" else "OPENAI"
    api_key = os.getenv(env_prefix + "_API_KEY", "")
    endpoint = args.endpoint or os.getenv("AZURE_OPENAI_ENDPOINT" if args.api_type == "azure" else "OPENAI_BASE_URL", "")
    if args.api_type == "openai" and not endpoint:
        endpoint = "https://api.openai.com/v1"
    model = args.model or os.getenv("AZURE_OPENAI_DEPLOYMENT" if args.api_type == "azure" else "OPENAI_MODEL", "gpt-4o" if args.api_type == "azure" else "gpt-4o-2024-11-20")
    if not api_key or not endpoint:
        raise SystemExit(f"Set {env_prefix}_API_KEY and the endpoint environment variable (or --endpoint).")
    base_url = nh.normalize_endpoint(endpoint, args.api_type)
    try:
        requests_version = importlib.metadata.version("requests")
    except importlib.metadata.PackageNotFoundError:
        raise SystemExit("Install the original code's dependency: python -m pip install requests")
    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    outdir = args.output_root.resolve() / args.phase / run_id
    config = {"run_id": run_id, "study_id": args.study_id, "protocol_version": nh.PROTOCOL_VERSION,
              "code_version": nh.CODE_VERSION, "phase": args.phase,
              "api_type": args.api_type, "base_url": base_url, "model": model,
              "model_condition": args.model_condition or f"{model}|{url_host(base_url)}|v4.1-new-experiment",
              "temperature": 0.0, "top_p": 1.0, "max_output_tokens": args.max_output_tokens,
              "max_extra_transport_retries": 2, "timeout_sec": args.timeout_sec,
              "pause_sec": args.pause_sec, "concurrency": 1, "random_seed": args.seed,
              "API_sampling_seed": None, "SDK": None, "requests_version": requests_version,
              "python_version": sys.version, "platform": platform.platform(),
              "store": False, "server_conversation": None, "previous_response_id": None,
              "history_truncation": False, "framing": args.framing,
              "bootstrap_replicates": args.bootstrap_replicates, "minimum_effect_of_interest": args.minimum_effect,
              "sample_size_rationale": "fixed resource budget in PDF; not a power guarantee",
              "stop_rule": "fixed planned schedule; keep invalid outcomes, no selective refill; stop on interrupt or fatal configuration error",
              "template_sha256": nh.sha256(prompt_templates()), "design_sha256": nh.sha256(plan),
              "original_paper_model_identifier": "gpt-4o-2024-11-20",
              "backend_version_verified_independently": False,
              "source_prompt_note": "PDF v4.1 section 6; print wrapping and quotation glyphs normalized"}
    archive = nh.Archive(outdir, api_key)
    archive.write_json("config.json", config)
    archive.write_json("design_manifest.json", plan)
    archive.write_json("prompts_en_v4_1.json", prompt_templates())
    (outdir / "prompts_en_v4_1.txt").write_text("\n\n".join(k+"\n"+v for k, v in prompt_templates().items()), encoding="utf-8")
    source_hashes = {}
    for p in (Path(__file__).resolve(), Path(nh.__file__).resolve()):
        content = p.read_bytes()
        (outdir / ("code_snapshot_" + p.name)).write_bytes(content)
        source_hashes[p.name] = hashlib.sha256(content).hexdigest()
    archive.write_json("source_hashes.json", source_hashes)
    print(f"Paired H0/H1 {args.phase}: {plan['planned_total']} scheduled requests before retries.", flush=True)
    print(f"Output directory: {outdir}", flush=True)
    client = nh.ChatClient(config, api_key, archive)
    rows, state = execute(plan, config, archive, client)
    pathrows = write_descriptive_outputs(plan, rows, archive)
    # Never publish inferential p-values on an optional-stopping partial dataset.
    if state == "completed" and args.phase == "formal":
        print("Computing paired r-block analysis...", flush=True)
        write_paired_analysis(plan, rows, pathrows, archive, config)
    print(f"Finished: {state}. Recorded {len(rows)}/{plan['planned_total']}. Saved to {outdir}", flush=True)
    if state != "completed":
        print("Partial records are preserved. This run is not complete; it will not silently restart or refill paths.")
    return 0 if state == "completed" else 2


def url_host(url):
    from urllib.parse import urlsplit
    return urlsplit(url).hostname


if __name__ == "__main__":
    sys.exit(main())
