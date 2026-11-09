# -*- coding: utf-8 -*-
"""测试用假客户端：实现被测命令需要的读/写面，数据来自 FAKE_WORLD（JSON）。

它不是产品代码，只用于"真 CLI 子进程 + 假数据源"的集成测试：
  · 读（`query`，batch GET）：items(listId) / channel_detail(channelId=...) /
    brandMentions.listJobs・getChartData・getTopChannels・getVideoEvidence
  · 读（`query_plain`，非 batch GET）：brandMentions.exportMentions
  · 读（`read_post`，平台登记为 mutation 动词的只读查询）：discovery.enrichChannels・enrichEmails
  · 写（`mutate`）：lists.batchAddItems
  · 每次调用追加一行到 FAKE_CALLS（测试据此断言"只读命令没有写请求"）

为什么把 `read_post` 与 `mutate` **分成两个方法**：被测的 `search enrich` 是只读命令，
测试要能**用代码核对**"它一次 `mutate` 都没发"。两者的区别不是 HTTP 动词（都是 POST），
而是语义与审计面（见 `daniel_client.Daniel.read_post` 的说明）。
"""
import json
import os

#: `daniel_mentions.py` 会 `from daniel_client import BASE`，缺了它连 import 都过不去。
BASE = "http://fake.local"
SESSION_FILE = "<fake-session>"


def _read_session_cookie():
    return ("fake-session-token", False)


class Daniel:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def login(self):
        return True

    def _world(self):
        with open(os.environ["FAKE_WORLD"], encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, world):
        path = os.environ.get("FAKE_WORLD")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(world, fh, ensure_ascii=False, indent=1)

    def _log(self, kind, **kw):
        path = os.environ.get("FAKE_CALLS")
        if not path:
            return
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, **kw}, ensure_ascii=False) + "\n")

    # ── 读（batch GET）──
    def query(self, route, inp=None, **kw):
        self._log("query", route=route, payload=inp)
        world = self._world()
        if route == "lists.getItems":
            return self.items((inp or {}).get("listId"))
        if route == "brandMentions.listJobs":
            return [dict(r) for r in (world.get("jobs") or [{"jobId": "job-1", "status": "done"}])]
        if route == "brandMentions.getChartData":
            return dict(world.get("chart") or {})
        if route == "brandMentions.getTopChannels":
            return [dict(r) for r in (world.get("topChannels") or [])]
        if route == "brandMentions.getVideoEvidence":
            return dict(world.get("evidence") or {})
        if route == "discovery.getSearchHistory":
            return []
        return []

    # ── 读（非 batch GET；导出类路由在前端就是这一形态）──
    def query_plain(self, route, inp=None, **kw):
        self._log("query_plain", route=route, payload=inp)
        world = self._world()
        if route == "brandMentions.exportMentions":
            return [dict(r) for r in (world.get("export") or [])]
        return []

    # ── 读（只读语义的 POST；不许用 mutate 代替）──
    def read_post(self, route, inp=None, **kw):
        self._log("read_post", route=route, payload=inp)
        world = self._world()
        enrich = world.get("enrich") or {}
        ids = list((inp or {}).get("channelIds") or [])
        if route == "discovery.enrichChannels":
            out = []
            for cid in ids:
                row = enrich.get(cid)
                if not row:
                    continue
                # 真实形状是**嵌套**的：{channelId, publicData:{...}}（seed_probe_mcgeee.py:94）
                out.append({"channelId": cid, "publicData": dict(row.get("publicData") or {})})
            return {"channels": out}
        if route == "discovery.enrichEmails":
            rows = []
            for cid in ids:
                pub = (enrich.get(cid) or {}).get("publicData") or {}
                mail = pub.get("businessEmail") or (enrich.get(cid) or {}).get("businessEmail")
                if mail:
                    rows.append({"channelId": cid, "email": mail})
            return {"results": rows}
        return {}

    def items(self, list_id):
        world = self._world()
        return [dict(r) for r in (world.get("lists") or {}).get(str(list_id), [])]

    def channel_detail(self, **kw):
        cid = kw.get("channelId")
        self._log("detail", channelId=cid)
        world = self._world()
        if cid in (world.get("failDetails") or []):
            raise RuntimeError("HTTP 500 模拟详情失败")
        return dict((world.get("details") or {}).get(cid) or {})

    def resolve_brand_ref(self, ref):
        return {"id": 3690002, "name": "Halliday", "workspaceId": 90002,
                "category": "AI Glasses", "competitors": []}

    # ── 写 ──
    def mutate(self, route, inp=None, **kw):
        self._log("mutate", route=route, payload=inp)
        if route != "lists.batchAddItems":
            return {}
        world = self._world()
        list_id = str((inp or {}).get("listId"))
        rows = world.setdefault("lists", {}).setdefault(list_id, [])
        items = list((inp or {}).get("items") or [])
        if (world.get("mutateMode") or "normal") == "drop_one":
            items = items[:-1]
        existing = {r.get("channelId") for r in rows}
        added = [dict(it) for it in items if it.get("channelId") not in existing]
        rows.extend(added)
        self._save(world)
        return {"addedCount": len(added), "failed": []}
