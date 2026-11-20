"""Backend of the offline rehearsal: runs the real contract in the direct runner and answers line-JSON requests.

It is started by rehearsal/run.sh (through pytest, because the direct runner lives in pytest fixtures) and talks to
the stub of genlayer-js over stdin and stdout. Nothing here touches a network. The model is a script: its answers
come from environment variables (see rehearsal/run.sh)."""

import json
import os
import sys
from datetime import datetime, timezone

from conftest import *  # noqa: F401,F403  (the same helpers as the unit tests)
from conftest import GEN, Wire, act, deploy

# the direct runner swaps file descriptor 0 for its own message, so keep a private copy of the real stdin first
_STDIN = os.fdopen(os.dup(0), "r")
MARK = "@@RPC "
READ_LEVEL = int(os.environ.get("READ_LEVEL", "0"))  # what the claims adjuster answers
APPEAL_LEVEL = int(os.environ.get("APPEAL_LEVEL", "-1"))  # what the appeals adjuster answers (-1: the same as the reading)
BIND_MODE = os.environ.get("BIND_MODE", "pass")  # pass | refuse
PAGE_QUOTE = "The reserved names include example.com, example.net and example.org."
PAGE_TEXT = (
    "<html><body><h1>Example domains</h1><p>Example domains are reserved by the IANA for documentation. "
    "They are maintained by the Internet Assigned Numbers Authority and can be used in documents without "
    f"permission. {PAGE_QUOTE}</p></body></html>"
)


def out(obj):
    sys.stdout.write(MARK + json.dumps(obj) + "\n")
    sys.stdout.flush()


def unbig(value):
    if isinstance(value, dict) and "$big" in value:
        return int(value["$big"])
    if isinstance(value, list):
        return [unbig(v) for v in value]
    return value


def check(ok, flags=(), reason="Scripted answer."):
    return json.dumps({"verdict": "PASS" if ok else "FAIL", "flags": list(flags), "reason": reason})


def reading(level):
    return json.dumps({"level": level, "quote": PAGE_QUOTE if level else "", "flags": [], "reason": "Scripted answer."})


def set_mocks(vm):
    vm.clear_mocks()
    vm.mock_web(r"iana\.org", {"status": 200, "body": PAGE_TEXT})
    # the more specific wordings first: the first matching mock answers
    vm.mock_llm(r"wording underwriter[\s\S]*opinion of whoever", check(False, ["vague", "subjective"], "The terms rest on feelings."))
    vm.mock_llm(r"wording underwriter[\s\S]*Level 1 is reached if the page contains", check(False, ["already_met"], "The page already contains this phrase."))
    if os.environ.get("VET_REFUSE_PRIMARY") == "1":  # the model dislikes the standard wording, so the fallback wording is used
        vm.mock_llm(r"wording underwriter[\s\S]*The policy looks only at", check(False, ["vague"], "The wording is not objective enough."))
    vm.mock_llm(r"wording underwriter", check(True))
    vm.mock_llm(r"inception inspector", check(BIND_MODE == "pass", [] if BIND_MODE == "pass" else ["already_met"]))
    vm.mock_llm(r"claims adjuster", reading(READ_LEVEL))
    vm.mock_llm(r"appeals adjuster", reading(READ_LEVEL if APPEAL_LEVEL < 0 else APPEAL_LEVEL))


def test_serve(direct_vm, direct_deploy):
    vm = direct_vm
    c = deploy(direct_deploy, vm)
    funded, spent = {}, {}
    out({"ready": True})
    for line in _STDIN:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        rid = req.get("id")
        try:
            now = int(req.get("now", 0))
            if now:
                vm.warp(datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            op = req["op"]
            if op == "fund":
                funded[req["address"].lower()] = funded.get(req["address"].lower(), 0) + int(req["amount"])
                out({"id": rid, "ok": True})
            elif op == "balance":
                addr = req["address"].lower()
                got = sum(v for a, v in Wire.sent if a == addr)
                out({"id": rid, "ok": True, "ret": str(funded.get(addr, 10 * GEN) + got - spent.get(addr, 0))})
            elif op == "view":
                set_mocks(vm)
                out({"id": rid, "ok": True, "ret": getattr(c, req["fn"])(*unbig(req["args"]))})
            elif op == "call":
                set_mocks(vm)
                args = unbig(req["args"])
                sender = bytes.fromhex(req["sender"][2:])
                value = int(req.get("value", 0))
                act(vm, sender, value)
                try:
                    getattr(c, req["fn"])(*args)
                finally:
                    vm.value = 0
                key = req["sender"].lower()
                spent[key] = spent.get(key, 0) + value  # only a call that was not refused moves the value
                out({"id": rid, "ok": True})
            else:
                out({"id": rid, "ok": False, "error": f"unknown op {op}"})
        except Exception as e:  # a refusal by the contract
            vm.value = 0
            out({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"[:400]})
