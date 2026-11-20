from conftest import *


def test_deploys_and_runs_the_happy_path(direct_vm, direct_deploy, ledger):
    c = deploy(direct_deploy, direct_vm)
    pid = read(c, direct_vm, 2)
    row = prow(c, pid)
    assert row["state"] == READ and row["level"] == 2
    settle(c, direct_vm, pid, offset=T_FREE)
    row = prow(c, pid)
    assert row["state"] == SETTLED and row["final_level"] == 2
    assert ledger.to(P.insured) == 60 * MILLI  # 60% of 0.1 GEN
    # backers: capital left (40) + premium (10) split 60:40
    assert ledger.to(P.b1) == 30 * MILLI and ledger.to(P.b2) == 20 * MILLI
    invariants(c)
