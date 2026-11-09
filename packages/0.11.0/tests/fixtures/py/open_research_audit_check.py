# -*- coding: utf-8 -*-
"""open 通道提交后的审计落盘检查（给 node:test 调用的 Python 夹具）。

为什么单独一个夹具：审计写进 `$DANIEL_HOME/logs/write-audit.jsonl` 是在 worker（Python）里做的；
node 侧只能通过"真跑一次 worker 的 op_open_submit ＋ 读审计文件"来证明它真的落盘了。
本夹具用假客户端/假检索仪器，不发任何网络请求。
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


class FakeClient:
    def query(self, route, payload=None, **kw):
        if route == "discovery.getSearchJob":
            return {"status": "queued", "progressCompleted": 0, "progressTotal": 0}
        return {}


class FakeSearch:
    MAX_QUERY_LEN = 501

    def expand_topic(self, d, topic):
        return {"scenarios": ["商务会议"], "contentStyles": ["评测"],
                "audiences": ["商务旅客"]}

    def open_payload(self, d, plan, trim=False):
        return {"payload": {"topic": plan["topic"], "brandId": 3690002},
                "brand": {"id": 3690002, "name": "Halliday"},
                "topic": plan["topic"]}

    def start_job(self, d, route, payload):
        return {"jobId": "job-audit-1", "execNote": ""}


def load_worker():
    path = os.path.join(PKG, "lib", "worker.py")
    spec = importlib.util.spec_from_file_location("daniel_worker_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    home = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="daniel-audit-")
    os.environ["DANIEL_HOME"] = home
    w = load_worker()
    w.client = lambda: FakeClient()
    w._search_mod = lambda: FakeSearch()
    out = w.op_open_submit({"topic": "AI glasses for business travel", "brand": "Halliday",
                            "country": "US", "minSubscribers": 10000})
    audit_path = os.path.join(home, "logs", "write-audit.jsonl")
    rows = []
    if os.path.isfile(audit_path):
        with open(audit_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    last = rows[-1] if rows else {}
    print(json.dumps({
        "ok": True,
        "home": home,
        "jobId": out.get("jobId"),
        "auditInResult": out.get("audit"),
        "auditPath": audit_path,
        "auditRows": len(rows),
        "last": {k: last.get(k) for k in
                 ("module", "command", "action", "target", "executed", "ok", "exitCode",
                  "readbackOk", "dryRun", "mutation")},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
