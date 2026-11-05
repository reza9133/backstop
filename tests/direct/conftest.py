"""Shared helpers for the direct-mode suite (genlayer-test fixtures)."""

import json
import sys
from datetime import datetime, timezone

import pytest

CONTRACT = "contracts/backstop.py"
MODULE = "_contract_backstop"
GEN = 10**18
MILLI = 10**15  # 0.001 GEN, the smallest commitment

# policy states, bond states
DRAFT, OPEN, FILLED, ACTIVE, READ, CONTESTED, SETTLED, REFUSED, LAPSED, VOID, CANCELLED = range(11)
BOND_NONE, BOND_HELD, BOND_REFUNDED, BOND_FORFEITED = range(4)
FINAL = (SETTLED, REFUSED, LAPSED, VOID, CANCELLED)
LIVE = (DRAFT, OPEN, FILLED, ACTIVE, READ, CONTESTED)

T0 = int(datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp())

TITLE = "Frankfurt region outage cover"
TERMS = (
    "Level 1 is reached if the status page reports at least one outage of the Frankfurt region that lasted more than "
    "one hour inside the cover period. Level 2 is reached if it reports an outage of more than four hours. Level 3 is "
    "reached if it reports a full regional outage of more than twelve hours."
)
SOURCE = "https://status.example.org/reports/frankfurt"
SOURCE_2 = "https://status.example.org/reports/paris"

PAGE_QUIET = (
    "<html><body><h1>Frankfurt region status</h1><p>All systems operational. No incidents were reported this month. "
    "Planned maintenance windows are announced one week in advance.</p></body></html>"
)
QUOTE_1 = "Frankfurt region outage lasted 90 minutes on the evening of the cover period"
QUOTE_2 = "Frankfurt region outage lasted 5 hours on the evening of the cover period"
QUOTE_3 = "Frankfurt region suffered a full regional outage of 14 hours during the cover period"
PAGE_1 = f"<html><body><h1>Frankfurt region status</h1><p>Incident report: the {QUOTE_1}. Service was restored afterwards.</p></body></html>"
PAGE_2 = f"<html><body><h1>Frankfurt region status</h1><p>Incident report: the {QUOTE_2}. Service was restored afterwards.</p></body></html>"
PAGE_3 = f"<html><body><h1>Frankfurt region status</h1><p>Incident report: the {QUOTE_3}. Service was restored afterwards.</p></body></html>"
QUOTES = {1: QUOTE_1, 2: QUOTE_2, 3: QUOTE_3}
PAGES = {0: PAGE_QUIET, 1: PAGE_1, 2: PAGE_2, 3: PAGE_3}

COVER = 100 * MILLI  # 0.1 GEN
PREMIUM = 10 * MILLI
TIERS = (2500, 6000, 10000)
BACKING, COVER_SECS, RESOLVE, CONTEST = 3600, 3600, 7200, 1800


def hx(a) -> str:
    """Lower-case 0x form of an address object, raw bytes or a hex string."""
    if isinstance(a, str):
        return a.lower()
    if hasattr(a, "as_hex"):
        return str(a.as_hex).lower()
    return "0x" + bytes(a).hex()


def at(vm, offset: int) -> None:
    """Move the chain clock to T0 + offset seconds."""
    vm.warp(datetime.fromtimestamp(T0 + offset, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def act(vm, who, value: int = 0):
    """The next call is made by `who` and carries `value`."""
    try:
        vm.deal(who, 1000 * GEN)
    except Exception:
        pass
    vm.sender = who
    vm.value = value


class Wire:
    """Stands in for the chain-level transfer so that payouts can be inspected."""

    sent = []

    def __init__(self, who):
        self.who = who

    def emit_transfer(self, **kw):
        Wire.sent.append((hx(self.who), int(kw["value"])))


class Ledger:
    def __init__(self):
        Wire.sent = []

    @property
    def sent(self):
        return Wire.sent

    def to(self, who) -> int:
        key = hx(who)
        return sum(v for a, v in Wire.sent if a == key)

    def total(self) -> int:
        return sum(v for _, v in Wire.sent)

    def count(self) -> int:
        return len(Wire.sent)


@pytest.fixture
def ledger():
    return Ledger()


def _forget_contract_class() -> None:
    """The SDK keeps one contract class per process; drop it so every test can deploy afresh."""
    for name in ("genlayer.gl.genvm_contracts", "genlayer.genvm_contracts"):
        registry = sys.modules.get(name)
        if registry is not None and hasattr(registry, "__known_contract__"):
            registry.__known_contract__ = None


def deploy(direct_deploy, direct_vm):
    at(direct_vm, 0)
    direct_vm.check_pickling = True  # the closures handed to the VM must be serializable
    _forget_contract_class()
    c = direct_deploy(CONTRACT)
    mod = sys.modules[MODULE]
    mod._Wire = Wire
    Wire.sent = []
    return c


def stats(c) -> dict:
    return json.loads(c.stats())


def books(c) -> dict:
    return json.loads(c.solvency())


def _lowered(row):
    """The contract reports checksummed addresses; the tests compare lower-case ones."""
    if isinstance(row, dict):
        for k, v in row.items():
            if k in ("insured", "who", "contested_by") and isinstance(v, str):
                row[k] = v.lower()
            elif k == "backers":
                for b in v:
                    _lowered(b)
    return row


def prow(c, pid: int) -> dict:
    return _lowered(json.loads(c.get_policy(pid)))


def stake_of(c, pid: int, who) -> int:
    for b in prow(c, pid)["backers"]:
        if b["who"] == hx(who):
            return int(b["amount"])
    return 0


class P:
    """Fixed actors, as raw 20-byte addresses."""

    insured = bytes([0xB0, 1]) + bytes(18)
    insured2 = bytes([0xB0, 2]) + bytes(18)
    b1 = bytes([0xB0, 3]) + bytes(18)
    b2 = bytes([0xB0, 4]) + bytes(18)
    b3 = bytes([0xB0, 5]) + bytes(18)
    stranger = bytes([0xB0, 6]) + bytes(18)
    keeper = bytes([0xB0, 7]) + bytes(18)
    extra = [bytes([0xB1, 20 + i]) + bytes(18) for i in range(30)]


ZERO_ADDRESS = "0x" + "0" * 40


# ---- mocks ---------------------------------------------------------------------------------------------------------


def mock_page(vm, body=PAGE_QUIET, pattern=r"status\.example\.org", status=200):
    vm.mock_web(pattern, {"status": status, "body": body})


def check_reply(ok=True, flags=(), reason="The wording is clear and nothing has happened yet."):
    return {"verdict": "PASS" if ok else "FAIL", "flags": list(flags), "reason": reason}


def read_reply(level=0, quote=None, flags=(), reason="The page matches the terms."):
    if quote is None:
        quote = QUOTES.get(level, "") if level else ""
    return {"level": level, "quote": quote, "flags": list(flags), "reason": reason}


def mock_vetter(vm, ok=True, flags=(), reason="The wording is clear and nothing has happened yet.", raw=None):
    vm.mock_llm(r"wording underwriter", raw if raw is not None else json.dumps(check_reply(ok, flags, reason)))


def mock_binder(vm, ok=True, flags=(), reason="Nothing has happened yet.", raw=None):
    vm.mock_llm(r"inception inspector", raw if raw is not None else json.dumps(check_reply(ok, flags, reason)))


def mock_reader(vm, level=0, quote=None, flags=(), reason="The page matches the terms.", raw=None):
    vm.mock_llm(r"claims adjuster", raw if raw is not None else json.dumps(read_reply(level, quote, flags, reason)))


def mock_appeals(vm, level=0, quote=None, flags=(), reason="The page matches the terms.", raw=None):
    vm.mock_llm(r"appeals adjuster", raw if raw is not None else json.dumps(read_reply(level, quote, flags, reason)))


def world(vm, page=PAGE_QUIET, status=200):
    vm.clear_mocks()
    mock_page(vm, body=page, status=status)


# ---- steps ---------------------------------------------------------------------------------------------------------


def create(
    c, vm, who=None, premium=PREMIUM, title=TITLE, terms=TERMS, source=SOURCE, coverage=COVER, tiers=TIERS,
    backing=BACKING, cover=COVER_SECS, resolve=RESOLVE, contest=CONTEST, offset=None,
) -> int:
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.insured, premium)
    pid = c.create_policy(title, terms, source, coverage, tiers[0], tiers[1], tiers[2], backing, cover, resolve, contest)
    vm.value = 0
    return pid


def vet(c, vm, pid, who=None, ok=True, flags=(), offset=None, page=PAGE_QUIET, status=200, **kw):
    world(vm, page, status)
    mock_vetter(vm, ok, flags, **kw)
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.stranger)
    c.vet(pid)


def back(c, vm, who, pid, amount, offset=None):
    if offset is not None:
        at(vm, offset)
    act(vm, who, amount)
    c.back(pid)
    vm.value = 0


def bind(c, vm, pid, who=None, ok=True, flags=(), offset=None, page=PAGE_QUIET, status=200, **kw):
    world(vm, page, status)
    mock_binder(vm, ok, flags, **kw)
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.stranger)
    c.bind(pid)


def resolve(c, vm, pid, level=0, who=None, offset=None, page=None, status=200, quote=None, flags=(), **kw):
    world(vm, PAGES[level] if page is None else page, status)
    mock_reader(vm, level, quote, flags, **kw)
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.stranger)
    c.resolve(pid)


def contest(c, vm, pid, who, claim="The page shows more than the reading says.", offset=None):
    if offset is not None:
        at(vm, offset)
    due = int(c.bond_due(pid))
    act(vm, who, due)
    c.contest(pid, claim)
    vm.value = 0
    return due


def appeal(c, vm, pid, level=0, who=None, offset=None, page=None, status=200, quote=None, flags=(), **kw):
    world(vm, PAGES[level] if page is None else page, status)
    mock_appeals(vm, level, quote, flags, **kw)
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.stranger)
    c.appeal(pid)


def settle(c, vm, pid, who=None, offset=None):
    if offset is not None:
        at(vm, offset)
    act(vm, who or P.stranger)
    c.settle(pid)


# ---- ready-made situations: each stops at one state, with the clock at a known offset -------------------------------

T_CREATE, T_VET, T_BACK, T_BIND = 0, 10, 20, 30
T_END = T_BIND + COVER_SECS  # the cover ends
T_READ = T_END + 100
T_FREE = T_READ + CONTEST  # the contest time is over


def opened(c, vm, **kw) -> int:
    pid = create(c, vm, offset=T_CREATE, **kw)
    vet(c, vm, pid, offset=T_VET)
    return pid


def filled(c, vm, split=(60 * MILLI, 40 * MILLI), backers=None, **kw) -> int:
    pid = opened(c, vm, **kw)
    who = backers or [P.b1, P.b2, P.b3][: len(split)]
    for i, (w, amount) in enumerate(zip(who, split)):
        back(c, vm, w, pid, amount, offset=T_BACK + i)
    return pid


def active(c, vm, **kw) -> int:
    pid = filled(c, vm, **kw)
    bind(c, vm, pid, offset=T_BIND)
    return pid


def read(c, vm, level=0, **kw) -> int:
    pid = active(c, vm, **kw)
    resolve(c, vm, pid, level, offset=T_READ)
    return pid


def contested(c, vm, level=1, by=None, **kw) -> int:
    pid = read(c, vm, level, **kw)
    contest(c, vm, pid, by or P.insured, offset=T_READ + 10)
    return pid


# ---- whole-contract checks -----------------------------------------------------------------------------------------


def fingerprint(c) -> str:
    """Everything observable about the contract, so that a refused call can be shown to change nothing."""
    s = stats(c)
    return json.dumps([s, books(c), [prow(c, i) for i in range(s["policies"])], list(Wire.sent)], sort_keys=True)


def refuse(c, vm, msg, fn, *args, who=None, value=0):
    """The call must be refused with `msg` in the error, and it must leave the contract exactly as it was."""
    if who is not None:
        act(vm, who, value)
    before = fingerprint(c)
    with vm.expect_revert(msg):
        fn(*args)
    vm.value = 0
    assert fingerprint(c) == before, "a refused call changed the contract"


def invariants(c) -> None:
    """The books and every policy must be consistent, whatever happened before."""
    s = stats(c)
    b = books(c)
    assert b["balanced"], b
    rows = [prow(c, i) for i in range(s["policies"])]
    prem = stakes = bonds = 0
    sent_total = sum(v for _, v in Wire.sent)
    assert sent_total == int(s["paid"]), (sent_total, s["paid"])
    for r in rows:
        funded = int(r["funded"])
        assert funded == sum(int(x["amount"]) for x in r["backers"]), r
        assert funded <= int(r["coverage"]), r
        assert len(r["backers"]) <= 12
        assert len({x["who"] for x in r["backers"]}) == len(r["backers"])
        assert r["insured"] not in {x["who"] for x in r["backers"]}
        if r["state"] in LIVE:
            prem += int(r["premium"])
            stakes += funded
            bonds += int(r["bond"]) if r["bond_state"] == BOND_HELD else 0
            assert r["insured_got"] == "0" and r["backers_got"] == "0"
        else:
            bond = int(r["bond"])
            assert int(r["insured_got"]) + int(r["backers_got"]) == int(r["premium"]) + funded + bond, r
            assert r["bond_state"] != BOND_HELD
        if r["state"] == FILLED or r["state"] in (ACTIVE, READ, CONTESTED, SETTLED):
            assert funded == int(r["coverage"]), r
        if r["state"] in (DRAFT, REFUSED):
            assert funded == 0
        if r["state"] == SETTLED:
            tier = 0 if r["final_level"] == 0 else r["tiers"][r["final_level"] - 1]
            payout = int(r["coverage"]) * tier // 10_000
            bond_to_insured = 0
            if r["bond_state"] == BOND_FORFEITED and r["contested_by"] != r["insured"]:
                bond_to_insured = int(r["bond"])
            insured_refund = int(r["bond"]) if r["bond_state"] == BOND_REFUNDED and r["contested_by"] == r["insured"] else 0
            assert int(r["insured_got"]) == payout + bond_to_insured + insured_refund, r
    assert (prem, stakes, bonds) == (int(b["premiums"]), int(b["stakes"]), int(b["bonds"])), (prem, stakes, bonds, b)
