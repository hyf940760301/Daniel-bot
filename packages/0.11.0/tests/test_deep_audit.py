# -*- coding: utf-8 -*-
"""deep 提交审计的回归测试（python3 -m unittest · 不联网 · 不碰真实落点）。

验的是**一条事实**：deep 通道提交成功后，`daniel account audit` 读的那份
`write-audit.jsonl` 里会多一条 `command=deep-research-commit` 的记录，
字段与 open 通道（`open-research-commit`）逐项对齐。

做法：DANIEL_HOME 指到临时目录（审计真的写盘，再用 CLI 的 `audit.read_records` 读回），
只把**网络层**换掉（`client`／`_search_mod`／`_job_read`），提交序列本身走真实代码。

跑法（包根目录下）：
  python3 -m unittest discover -s tests -p 'test_*.py' -v
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PKG, "lib"))
sys.path.insert(0, os.path.join(PKG, "vendor", "data", "daniel-cli"))

import worker  # noqa: E402
from daniel_cli import audit as cli_audit  # noqa: E402

DEEP_QUERY = "AI glasses review and hands-on test"
BRAND = {"id": 3690002, "name": "Halliday", "category": "AI Glasses",
         "workspaceId": 90002, "competitors": []}


class _FakeSearch:
    """只实现两条通道用到的那几个函数；其余属性故意不给（缺了就会失败，不会静默跳过）。"""

    MAX_QUERY_LEN = 501

    def deep_payload(self, _client, plan, trim=False):
        return {"brand": dict(BRAND), "query": DEEP_QUERY, "note": None,
                "payload": {"brandId": BRAND["id"], "brandName": BRAND["name"],
                            "query": DEEP_QUERY, "limit": 10}}

    def start_job(self, _client, route, payload):
        assert payload.get("brandId") == BRAND["id"], payload
        if route == "discovery.startSearchJob":   # deep commit
            return {"jobId": "job-deep-1", "execNote": None}
        if route == "discovery.search":           # open commit
            return {"jobId": "job-open-1", "execNote": None}
        raise AssertionError("意外的提交路由：%s" % route)

    def expand_topic(self, _client, _topic):
        return {"scenarios": ["国际商务会议"], "contentStyles": ["智能眼镜评测"],
                "audiences": ["国际商务旅客"]}

    def open_payload(self, _client, plan, trim=False):
        return {"topic": plan["topic"], "brand": dict(BRAND),
                "payload": {"topic": plan["topic"], "brandId": BRAND["id"]}}


class DeepCommitAuditTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="daniel-audit-home-")
        self.env = mock.patch.dict(os.environ, {"DANIEL_HOME": self.home})
        self.env.start()
        patcher = mock.patch.multiple(
            worker,
            _search_mod=lambda: _FakeSearch(),
            client=lambda: object(),
            _job_read=lambda _d, _job_id: {"status": "queued", "progressCompleted": 0,
                                           "progressTotal": 0, "foundCount": 0},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.env.stop)

    def _rows(self):
        return cli_audit.read_records(out_dir=os.path.join(self.home, "logs"))

    def test_deep_commit_writes_one_audit_row(self):
        self.assertEqual(self._rows(), [], "起点：审计文件为空")

        out = worker.op_research_submit({"brand": "Halliday", "query": DEEP_QUERY, "limit": 10})
        self.assertEqual(out["jobId"], "job-deep-1")
        self.assertTrue(out["audit"]["已落盘"], out["audit"])

        rows = self._rows()
        self.assertEqual(len(rows), 1, "deep 提交后审计里应恰好多一条")
        row = rows[0]
        # —— 与 open 逐项对齐的字段 ——
        self.assertEqual(row["module"], "search")
        self.assertEqual(row["command"], "deep-research-commit")
        self.assertEqual(row["action"], "提交品牌深度研究检索任务")
        self.assertEqual(row["target"], DEEP_QUERY)
        self.assertEqual(row["brand"], "Halliday")
        self.assertIn("品牌深度研究", row["impact"])
        self.assertIs(row["dryRun"], False)
        self.assertIs(row["executed"], True)
        self.assertIs(row["ok"], True)
        self.assertEqual(row["exitCode"], 0)
        self.assertEqual(row["mutation"]["route"], "discovery.startSearchJob")
        self.assertEqual(row["mutation"]["request"]["brandId"], BRAND["id"])
        self.assertEqual(row["mutation"]["request"]["limit"], 10, "条数按入参记，不从 payload 猜")
        self.assertEqual(row["readback"]["jobId"], "job-deep-1")
        self.assertIs(row["readbackOk"], True)
        self.assertIs(row["rolledBack"], False)
        self.assertTrue(row["time"], "必须带落盘时间")
        self.assertTrue(row["ts"], "必须带时间戳")
        self.assertTrue(out["audit"]["路径"].endswith("write-audit.jsonl"), out["audit"]["路径"])
        # 交付里贴的就是这一行（真实读回，不是构造出来的对象）
        print("AUDIT-ROW " + json.dumps(row, ensure_ascii=False))

    def test_open_still_uses_its_own_command_and_same_file(self):
        worker.op_research_submit({"brand": "Halliday", "query": DEEP_QUERY})
        out = worker.op_open_submit({"topic": "AI glasses for business travel"})
        self.assertTrue(out["audit"]["已落盘"], out["audit"])

        rows = self._rows()
        self.assertEqual([r["command"] for r in rows],
                         ["deep-research-commit", "open-research-commit"],
                         "两条通道写的是同一份审计文件，command 各自可辨")
        deep, open_row = rows
        self.assertEqual(set(deep.keys()), set(open_row.keys()), "字段集必须完全一致")
        self.assertEqual(open_row["target"], "AI glasses for business travel")


if __name__ == "__main__":
    unittest.main()
