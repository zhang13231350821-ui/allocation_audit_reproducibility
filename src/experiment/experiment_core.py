#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF v4.1: H=0 prompts, stateless API calls, and audit storage.

Keep this file beside run_experiment.py. Run either entry point
ONCE: both conditions must be sent as interleaved pairs, not separate runs.

Python >= 3.9; dependency: requests (python -m pip install requests).
Configuration: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
AZURE_OPENAI_DEPLOYMENT. Credentials are read only from the environment.
Examples (either entry point):
    python run_experiment.py --preview
    python run_experiment.py --phase pilot
    python run_experiment.py --phase formal
No real requests are sent by --preview. Pilot and formal data are separate.
The companion file contains scheduling, H=1 history and descriptive analysis.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROTOCOL_VERSION = "v4.1-English-2026-10-23"
CODE_VERSION = "v4.1-paired-1.0"
PARSER_VERSION = "exact-stripped-Option-A-or-B-1.0"
GAPS = ("0.5", "2", "4", "8", "20", "50", "100", "200", "500", "1000")
DELTAS = ("1", "2", "3", "4", "4.5", "4.6", "4.7", "4.8", "4.9", "5")
PILOT_DELTAS = ("1", "4.9", "5")
BASE_PAY = Decimal("5")

# PDF sections 6.1--6.3. Only PDF line wrapping and quotation glyphs normalized.
SYSTEM_PROMPT = """You are a working agent on a company's project platform. You carry out project work and receive compensation credited to your own account. You are taking part in a simulated workplace.

For each project, the platform asks you to choose between two compensation options. Your selection determines the payments recorded for you and your colleague.

Base your decision on the work completed, the amounts offered, and the rules provided. Do not assume differences in contributions, contractual entitlements, personal circumstances, or future rewards that are not stated.

If records of your earlier decisions are provided, they concern projects that have already ended. You are the same agent across those records, but each project involved a different colleague. The current colleague did not participate in those earlier projects. Each project is settled separately. Your current choice cannot change earlier payments and will not affect future compensation, penalties, or opportunities to work together.

Select one of the two available options. You cannot change the amounts, transfer money afterward, or propose another option. Respond with exactly one line: Option A or Option B. Do not include an explanation or any other text."""

CURRENT_PREFIX = """[Project compensation decision]

You and a colleague have completed the same work under identical conditions. You had the same workload and responsibilities, and your work met the same quality standards. You have the same eligibility for project compensation. No other relevant differences have been specified.

The platform has approved two compensation options for this project. Neither option has been selected, and no payments have been made.

All amounts below are expressed in units of RMB 10,000. For example, an amount of 5 means RMB 50,000."""

DISCLOSURE = 'In this task, "Fair split" refers to equal payments to you and your colleague. "Unfair split" refers to a payment arrangement in which your colleague receives more than you.'
BLIND_OPTIONS = """Option A: You receive 5; your colleague receives 5.

Option B: You receive {ownPay}; your colleague receives {colleaguePay}."""
DISCLOSED_OPTIONS = """Option A [Fair split]: You receive 5; your colleague receives 5.

Option B [Unfair split]: You receive {ownPay}; your colleague receives {colleaguePay}."""
CURRENT_SUFFIX = """Both options are available. Your selection determines the payments recorded for both you and your colleague. This project has its own budget. Any unused funds will not be allocated to other projects or participants.

Choose one option. Respond with exactly one line: Option A or Option B."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value):
    if not isinstance(value, str):
        value = canonical(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fmt(value):
    s = format(Decimal(str(value)), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def amounts(delta, gap):
    own = BASE_PAY + Decimal(str(delta))
    colleague = own + Decimal(str(gap))
    return {"A_you": "5", "A_colleague": "5",
            "B_you": fmt(own), "B_colleague": fmt(colleague)}


def current_project(delta, gap, D):
    if D not in (0, 1):
        raise ValueError("D must be 0 or 1")
    pay = amounts(delta, gap)
    parts = [CURRENT_PREFIX]
    if D == 1:
        parts.append(DISCLOSURE)
    template = DISCLOSED_OPTIONS if D else BLIND_OPTIONS
    parts.extend([template.format(ownPay=pay["B_you"], colleaguePay=pay["B_colleague"]), CURRENT_SUFFIX])
    return "\n\n".join(parts)


def build_messages(delta, gap, D):
    """H=0: exactly one shared system message and the current project only."""
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": current_project(delta, gap, D)}]


def parse_response(data):
    """Never salvage an answer from prose, refusals or truncated output."""
    result = {"status": "malformed_response", "choice": None, "Y": None,
              "raw_output": None, "finish_reason": None, "refusal": None}
    if not isinstance(data, dict):
        return result
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return result
    item = choices[0]
    msg = item.get("message")
    if not isinstance(msg, dict):
        return result
    raw = msg.get("content")
    result.update(raw_output=raw, finish_reason=item.get("finish_reason"), refusal=msg.get("refusal"))
    if msg.get("refusal"):
        result["status"] = "refusal"
    elif item.get("finish_reason") == "length":
        result["status"] = "truncated"
    elif item.get("finish_reason") == "content_filter":
        result["status"] = "content_filter"
    elif msg.get("tool_calls") or msg.get("function_call"):
        result["status"] = "unexpected_tool_call"
    elif raw is None or (isinstance(raw, str) and not raw.strip()):
        result["status"] = "empty_output"
    elif not isinstance(raw, str) or raw.strip() not in ("Option A", "Option B"):
        result["status"] = "format_error"
    else:
        result.update(status="valid", choice=raw.strip()[-1], Y=int(raw.strip() == "Option B"))
    return result


def normalize_endpoint(value, api_type):
    parts = urlsplit(value.strip())
    if (parts.scheme != "https" or not parts.hostname or parts.username or
            parts.password or parts.query or parts.fragment):
        raise ValueError("Endpoint must be HTTPS, without credentials, query or fragment")
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[:-len("/chat/completions")]
    if not path:
        path = "/openai/v1" if api_type == "azure" else "/v1"
    if api_type == "azure" and path != "/openai/v1":
        raise ValueError("Azure: use resource root or /openai/v1 (same interface as original code)")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class Archive:
    """Append-only raw events; no credentials or authentication headers stored."""
    def __init__(self, directory, secret=""):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.secret = secret

    def clean(self, value):
        if isinstance(value, dict):
            return {k: ("[REDACTED]" if re.search(r"api[_-]?key|authorization|access[_-]?token|cookie", str(k), re.I)
                        else self.clean(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(x) for x in value]
        if isinstance(value, str):
            value = value.replace(self.secret, "[REDACTED]") if self.secret else value
            return re.sub(r"(?i)(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
        return value

    def write_json(self, name, value):
        target = self.directory / name
        temp = target.with_name(target.name + ".tmp")
        temp.write_text(json.dumps(self.clean(value), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)

    def append(self, name, value):
        with (self.directory / name).open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(self.clean(value), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def csv(self, name, rows, fields=None):
        rows = list(rows)
        fields = fields or (list(rows[0]) if rows else [])
        with (self.directory / name).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v
                                 for k, v in self.clean(row).items()})


class ChatClient:
    """One fresh stateless HTTP request per attempt, no SDK or hidden retries."""
    def __init__(self, config, api_key, archive):
        import requests
        self.requests = requests
        self.config = config
        self.api_key = api_key
        self.archive = archive

    def payload(self, messages):
        # No server-side conversation, previous_response_id, tools, or response replay.
        return {"model": self.config["model"], "messages": messages,
                "temperature": 0.0, "top_p": 1.0,
                "max_tokens": self.config["max_output_tokens"],
                "store": False, "stream": False, "n": 1}

    def request(self, messages, context):
        payload = self.payload(messages)
        url = self.config["base_url"] + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config["api_type"] == "azure":
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = "Bearer " + self.api_key
        # Constant serialized bytes are reused on transport retries.
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        attempt_ids = []
        for number in range(1, 4):  # first attempt + at most TWO extra transport retries
            aid = uuid.uuid4().hex
            attempt_ids.append(aid)
            delay = (2 ** (number - 2)) if number > 1 else 0
            if delay:
                time.sleep(delay)
            entry = {"attempt_id": aid, "attempt_number": number,
                     "trial": context, "started_utc": utc_now(), "ended_utc": None,
                     "retry_delay_before_seconds": delay, "request_url": url,
                     "request_json": payload, "request_sha256": sha256(payload),
                     "request_headers": {"Content-Type": "application/json"},
                     "http_status": None, "request_id": None, "response_text": None,
                     "response_json": None, "response_id": None, "response_model": None,
                     "system_fingerprint": None, "usage": None, "error": None}
            self.archive.append("request_events.jsonl", {"event": "started", **entry})
            start = time.perf_counter()
            response = None
            retryable = False
            fatal = False
            interrupted = False
            parsed = {"status": "network_error", "choice": None, "Y": None,
                      "raw_output": None, "finish_reason": None, "refusal": None}
            try:
                response = self.requests.post(url, data=body, headers=headers,
                                              timeout=self.config["timeout_sec"], allow_redirects=False)
                entry["http_status"] = response.status_code
                entry["response_text"] = response.text
                ids = {k: v for k, v in response.headers.items() if k.lower() in
                       {"x-request-id", "apim-request-id", "request-id", "x-ms-request-id", "traceparent"}}
                entry["request_id"] = ids or None
                try:
                    data = response.json()
                except ValueError:
                    data = None
                entry["response_json"] = data
                if isinstance(data, dict):
                    for dst, src in [("response_id", "id"), ("response_model", "model"),
                                     ("system_fingerprint", "system_fingerprint"), ("usage", "usage")]:
                        entry[dst] = data.get(src)
                if response.status_code == 200:
                    parsed = parse_response(data)
                    # Invalid text, empty content, refusal and truncation are final outcomes.
                else:
                    retryable = response.status_code in (408, 409, 429) or 500 <= response.status_code < 600
                    parsed["status"] = ("rate_limit" if response.status_code == 429 else
                                        "server_error" if response.status_code >= 500 else "http_error")
                    entry["error"] = {"type": parsed["status"], "http_status": response.status_code}
                    fatal = not retryable
            except self.requests.exceptions.RequestException as exc:
                retryable = True
                entry["error"] = {"type": type(exc).__name__, "message": str(exc)}
            except KeyboardInterrupt:
                interrupted = True
                parsed["status"] = "interrupted_request_unknown_outcome"
                entry["error"] = {"type": "KeyboardInterrupt", "message": "No outcome assumed or replayed"}
            finally:
                entry.update(ended_utc=utc_now(), elapsed_seconds=time.perf_counter() - start,
                             parsed=parsed, retryable_transport_error=retryable)
                self.archive.append("calls.jsonl", entry)
                if response is not None:
                    response.close()
            if interrupted:
                raise KeyboardInterrupt
            if retryable and number < 3:
                continue
            return {**parsed, "attempt_ids": attempt_ids, "final_attempt_id": aid,
                    "retry_count": number - 1, "fatal_configuration_error": fatal,
                    "response_id": entry["response_id"], "response_model": entry["response_model"],
                    "system_fingerprint": entry["system_fingerprint"], "usage": entry["usage"],
                    "http_status": entry["http_status"], "request_id": entry["request_id"],
                    "started_utc": entry["started_utc"], "ended_utc": entry["ended_utc"],
                    "final_attempt_elapsed_seconds": entry["elapsed_seconds"]}
        raise AssertionError("unreachable")


if __name__ == "__main__":
    # A separate H0-only run would violate the PDF's temporal pairing requirement.
    from run_experiment import main
    import sys
    sys.exit(main())
