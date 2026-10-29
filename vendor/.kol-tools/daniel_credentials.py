#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daniel Copilot 凭据存储（TICKET-144 · P0-1）—— 加密优先，明文只做**显式降级**。

解析顺序（**先加密后明文**）
  ① 系统钥匙串（macOS `security`，service 默认 `daniel-copilot`，account=邮箱）
  ② 环境变量 `DANIEL_EMAIL` / `DANIEL_PASSWORD`
  ③ **旧**明文文件 `<工作区根>/.daniel_cred.json`（只读兼容，不修改、不迁移、不打印内容；用则打警告）
  ④ 新明文降级文件 `$DANIEL_HOME/secrets/credentials.json`（**只有** `DANIEL_ALLOW_PLAINTEXT=1` 才用；
     权限 600，用则打警告）

纪律
  - 本模块**从不**把密码写到 stdout；`store-get` 只回"是否存在/来源/掩码邮箱"。
  - 非交互（沙箱/CI）下钥匙串写入会被系统拒绝 —— 此时 `store-set` 以非零退出并给出指引，**不静默降级**。
  - 钥匙串命令走 argv 传密码（macOS `security` CLI 的既定用法）；真机请在本机终端执行。

命令行
  python3 daniel_credentials.py store-status
  python3 daniel_credentials.py store-set --email you@x.com --password-stdin   # 或 --from-legacy
  python3 daniel_credentials.py store-get        # 只回是否存在/来源（不回显密码）
  python3 daniel_credentials.py store-delete
"""
import argparse
import getpass
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _sibling(name):
    """加载同目录模块（本文件既可被 import，也可被 `python3 daniel_credentials.py` 直接跑）。"""
    import importlib.util
    if HERE not in sys.path:
        sys.path.append(HERE)
    mod = sys.modules.get(name)
    if mod is not None and os.path.dirname(os.path.abspath(getattr(mod, "__file__", "") or "")) == HERE:
        return mod
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


dpaths = _sibling("daniel_paths")

DEFAULT_SERVICE = "daniel-copilot"
#: 旧明文凭据位置（**TICKET-194 起默认不可读**：必须落在 DANIEL_HOME 之内 ＋ 显式开关
#: `DANIEL_ALLOW_LEGACY_CRED=1`；判据的唯一真源是 `daniel_paths.legacy_allowed()`）。
#: 这里**不在模块级把它算成常量** —— 落点会随 `DANIEL_HOME` 注入而变化，且"允许读"是个
#: 每次都要现算的判定（含环境变量开关）。
def legacy_cred_file():
    """**可读的**旧明文凭据路径；被判拒读时返回 None（调用方据此不去读）。"""
    return dpaths.resolve("legacy_credentials_fallback")


def legacy_cred_declared():
    """旧明文凭据的**声明路径**（不看是否允许读；用于如实报出"这里本来有个旧位置"）。"""
    return dpaths.legacy_declared("credentials_fallback")


def legacy_cred_gate():
    """旧明文凭据位置的判定 `(是否允许读, 原因码, 人话)`。"""
    return dpaths.legacy_allowed("credentials_fallback")


def legacy_switch_on():
    return os.environ.get(dpaths.ALLOW_LEGACY_CRED_ENV) == "1"


PLAINTEXT_FILE = dpaths.resolve("credentials_fallback")              # $DANIEL_HOME/secrets/credentials.json

_warned = set()


def keychain_service():
    return os.environ.get("DANIEL_KEYCHAIN_SERVICE") or DEFAULT_SERVICE


def mask_email(email):
    """只暴露形状，不暴露值：jack.hu@example.com → j***@***.com"""
    s = str(email or "").strip()
    if not s:
        return ""
    if "@" not in s:
        return s[0] + "***"
    local, _, dom = s.partition("@")
    tld = ("." + dom.rsplit(".", 1)[1]) if "." in dom else ""
    return "%s***@***%s" % (local[:1], tld)


def _warn(msg):
    """同一进程内同类警告只打一次（避免刷屏）。"""
    if msg in _warned:
        return
    _warned.add(msg)
    print("⚠️  " + msg, file=sys.stderr)


def warn_plaintext_legacy():
    _warn("正在使用**旧明文凭据文件**：%s（只读兼容，内容未改动；本次已显式打开 %s=1）。"
          "建议迁到系统钥匙串：python3 %s store-set --from-legacy"
          % (legacy_cred_file(), dpaths.ALLOW_LEGACY_CRED_ENV,
             os.path.relpath(__file__, dpaths.ROOT)))


def warn_plaintext_fallback():
    _warn("正在使用**明文降级凭据文件**（DANIEL_ALLOW_PLAINTEXT=1）：%s（权限 600）。"
          "建议迁到系统钥匙串：python3 %s store-set --from-legacy"
          % (PLAINTEXT_FILE, os.path.relpath(__file__, dpaths.ROOT)))


# ────────────────────────── 钥匙串（macOS security） ──────────────────────────
def security_bin():
    """钥匙串 CLI 路径。`DANIEL_SECURITY_BIN` 可替换（非 macOS 的包装器／自检用的假 CLI）。"""
    return os.environ.get("DANIEL_SECURITY_BIN") or "/usr/bin/security"


def _security(args):
    """跑 `security`，返回 (returncode, stdout, stderr)。找不到命令 → (127, '', reason)。"""
    try:
        p = subprocess.run([security_bin()] + list(args),
                           capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        try:
            p = subprocess.run(["security"] + list(args), capture_output=True, text=True, timeout=20)
        except FileNotFoundError:
            return 127, "", "security CLI 不存在（非 macOS）"
    except Exception as e:                                          # noqa: BLE001
        return 126, "", str(e)
    return p.returncode, p.stdout, p.stderr


def keychain_available():
    rc, _, _ = _security(["-h"])
    return rc not in (127, 126)


def _keychain_account():
    """从条目属性里读出 account（`"acct"<blob>="…"`）。"""
    rc, out, _ = _security(["find-generic-password", "-s", keychain_service()])
    if rc != 0:
        return None
    m = re.search(r'^\s*"acct"<blob>="(.*)"\s*$', out, re.M)
    return m.group(1).replace('\\"', '"') if m else None


def keychain_find(account=None):
    """返回 (email, password) 或 (None, None)。**不打印任何值**。

    ① 显式 pin 的 account（`DANIEL_KEYCHAIN_ACCOUNT`）→ 只按它查，查不到就返回 None；
    ② 否则先按 `DANIEL_EMAIL`（当账号提示）查，再退化为"读条目属性拿 account"再查 —— 保证
       **只要钥匙串里有本 service 的条目就一定优先于环境变量/明文文件**。
    """
    svc = keychain_service()
    pinned = os.environ.get("DANIEL_KEYCHAIN_ACCOUNT") or account
    cands = []
    if pinned:
        cands.append(pinned)
    else:
        if os.environ.get("DANIEL_EMAIL"):
            cands.append(os.environ["DANIEL_EMAIL"])
        acct = _keychain_account()
        if acct:
            cands.append(acct)
    for acct in cands:
        if not acct:
            continue
        rc, out, _ = _security(["find-generic-password", "-s", svc, "-a", acct, "-w"])
        if rc == 0:
            return acct, out.rstrip("\n")
    return None, None


def keychain_set(email, password):
    """写/更新钥匙串条目。返回 (ok, message)。message 里**不含密码**。"""
    rc, _, err = _security(["add-generic-password", "-U", "-s", keychain_service(),
                            "-a", str(email), "-w", str(password)])
    if rc == 0:
        return True, "ok"
    hint = ""
    low = (err or "").lower()
    if "operation not permitted" in low or "interaction not allowed" in low:
        hint = ("｜系统/沙箱拒绝写钥匙串：请在**本机交互式终端**执行同一条命令"
                "（DSH 沙箱为 workspace-write 时会拒绝对 ~/Library/Keychains 的写入）。")
    return False, ("%s%s" % ((err or "").strip(), hint)).strip()


def keychain_delete(email=None):
    svc = keychain_service()
    acct = email or os.environ.get("DANIEL_KEYCHAIN_ACCOUNT") or os.environ.get("DANIEL_EMAIL") or None
    if not acct:
        acct = _keychain_account()
        if not acct:
            return False, "钥匙串里没有 service=%s 的条目" % svc
    rc, _, err = _security(["delete-generic-password", "-s", svc, "-a", acct])
    return (rc == 0), (err or "").strip()


# ────────────────────────── 明文（兼容读 / 显式降级写） ──────────────────────────
def _read_json_cred(path):
    """读 JSON 凭据文件，返回 (email, password)；路径为空/文件不存在/不合法 → (None, None)。

    `path` 为空（`None`／空串）＝ **该落点被判拒读**（TICKET-194：越界的旧位置不再被读），
    这里直接返回 `(None, None)`，绝不因为路径为空而抛异常。
    """
    if not path or not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:                                               # noqa: BLE001
        return None, None
    if not isinstance(d, dict):
        return None, None
    email, pw = d.get("email"), d.get("password")
    if email and pw:
        return email, pw
    return None, None


def plaintext_fallback_enabled():
    return os.environ.get("DANIEL_ALLOW_PLAINTEXT") == "1"


def plaintext_write(email, password):
    """显式降级：写 $DANIEL_HOME/secrets/credentials.json（权限 600）。"""
    if not plaintext_fallback_enabled():
        return False, "未启用明文降级：需显式设置 DANIEL_ALLOW_PLAINTEXT=1"
    d = os.path.dirname(PLAINTEXT_FILE)
    if not dpaths.ensure_dir(d):
        return False, "无法创建目录 %s" % d
    tmp = PLAINTEXT_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"email": email, "password": password}, f)
            f.flush()
            os.fsync(f.fileno())
    finally:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, PLAINTEXT_FILE)
    os.chmod(PLAINTEXT_FILE, 0o600)
    warn_plaintext_fallback()
    return True, PLAINTEXT_FILE


# ────────────────────────── 统一解析 ──────────────────────────
class DanielCredentialStore:
    """凭据来源解析与写入。`get()` 返回 (email, password, source)。"""

    SOURCES = ("keychain", "env", "legacy_plaintext_file", "plaintext_fallback", "none")

    def get(self, allow_plaintext=True):
        email, pw = keychain_find()
        if email and pw:
            return email, pw, "keychain"
        e2, p2 = os.environ.get("DANIEL_EMAIL"), os.environ.get("DANIEL_PASSWORD")
        if e2 and p2:
            return e2, p2, "env"
        if allow_plaintext:
            # 🔴 TICKET-194 · C：旧明文文件只在"落在 DANIEL_HOME 之内 ＋ 显式开关已打开"
            # 时才进入候选（默认关）。被拒时 legacy_cred_file() 返回 None ⇒ 读不到任何东西。
            e3, p3 = _read_json_cred(legacy_cred_file())
            if e3 and p3:
                warn_plaintext_legacy()
                return e3, p3, "legacy_plaintext_file"
            e4, p4 = _read_json_cred(PLAINTEXT_FILE)
            if e4 and p4:
                warn_plaintext_fallback()
                return e4, p4, "plaintext_fallback"
        return None, None, "none"

    def status(self):
        """只回"是否存在/来源/掩码"，**不回显密码**。"""
        email, pw = keychain_find()
        kc = {"service": keychain_service(), "available": keychain_available(),
              "found": bool(email and pw), "account_masked": mask_email(email)}
        env_set = bool(os.environ.get("DANIEL_EMAIL") and os.environ.get("DANIEL_PASSWORD"))
        legacy_path_now = legacy_cred_file()
        legacy_ok, legacy_code, legacy_why = legacy_cred_gate()
        legacy_exists = bool(legacy_path_now) and os.path.exists(legacy_path_now)
        le, _ = _read_json_cred(legacy_path_now)
        plain_exists = os.path.exists(PLAINTEXT_FILE)
        _, _, source = self.get()
        return {
            "source": source,
            "exists": source != "none",
            "email_masked": mask_email(email or os.environ.get("DANIEL_EMAIL") or le or ""),
            "keychain": kc,
            "env": {"set": env_set, "email_masked": mask_email(os.environ.get("DANIEL_EMAIL"))},
            # 旧明文凭据：**如实报出"声明路径／是否允许读／为什么"**（被拒时 path 为 None，
            # 同时给 declaredPath 让人看得到"这里本来有个旧位置"）—— 不许静默。
            "legacy_plaintext_file": {"path": legacy_path_now,
                                      "declaredPath": legacy_cred_declared(),
                                      "allowed": bool(legacy_ok), "reason": legacy_why,
                                      "reasonCode": legacy_code,
                                      "switchOn": legacy_switch_on(),
                                      "switchEnv": dpaths.ALLOW_LEGACY_CRED_ENV,
                                      "exists": legacy_exists,
                                      "usable": bool(le)},
            "plaintext_fallback": {"path": PLAINTEXT_FILE, "exists": plain_exists,
                                   "enabled": plaintext_fallback_enabled()},
            "encrypted_first": source in ("keychain", "env"),
        }

    def set(self, email, password, allow_plaintext_fallback=True):
        ok, msg = keychain_set(email, password)
        if ok:
            return True, "keychain", "已写入系统钥匙串（service=%s）" % keychain_service()
        if allow_plaintext_fallback and plaintext_fallback_enabled():
            ok2, msg2 = plaintext_write(email, password)
            if ok2:
                return True, "plaintext_fallback", "钥匙串写入失败（%s）；已按显式降级写入 %s" % (msg, msg2)
            return False, "none", "钥匙串写入失败（%s）；明文降级也失败（%s）" % (msg, msg2)
        return False, "none", "钥匙串写入失败：%s" % msg

    def delete(self):
        return keychain_delete()


def resolve_credentials():
    """给 daniel_client 用：返回 (email, password)，无凭据时抛 SystemExit（文案与改造前一致口径）。"""
    email, pw, src = DanielCredentialStore().get()
    if email and pw:
        return email, pw
    raise SystemExit(
        "本机没有可用的 Daniel 凭据（也没有会话）。\n"
        "· **给人用的主路径**：`daniel account login --browser` —— 打开 Daniel 登录页，"
        "在页面上完成登录，再把会话粘回 CLI（CLI 先校验后落盘）\n"
        "· 无头／CI 备用路：设置 DANIEL_EMAIL／DANIEL_PASSWORD 后 "
        "`daniel account login --confirm`（**不是给人用的主路径**）\n"
        "· 把凭据写进本机钥匙串：`daniel account credentials set --from-env --confirm`"
        "（或 python3 .kol-tools/daniel_credentials.py store-set --password-stdin）\n"
        "🔴 旧明文文件 %s **默认不再被读取**（TICKET-194：越界读点已封）；"
        "确实要临时兼容，需把它放进数据落点之内并显式设置 %s=1。"
        % (legacy_cred_declared(), dpaths.ALLOW_LEGACY_CRED_ENV))


# ────────────────────────── CLI ──────────────────────────
def _cmd_status(_a):
    print(json.dumps(DanielCredentialStore().status(), ensure_ascii=False, indent=1))
    return 0


def _cmd_get(_a):
    email, _pw, src = DanielCredentialStore().get()
    print(json.dumps({"exists": bool(email and _pw), "source": src,
                      "email_masked": mask_email(email)}, ensure_ascii=False, indent=1))
    return 0 if (email and _pw) else 1


def _cmd_set(a):
    email, password = a.email, None
    if a.from_legacy:
        email, password = _read_json_cred(legacy_cred_file())
        if not password:
            ok_l, code_l, why_l = legacy_cred_gate()
            print("旧明文文件不可用：%s" % why_l, file=sys.stderr)
            if not ok_l:
                print("（该落点被判拒读：%s；这是 TICKET-194 的默认行为，"
                      "要临时兼容旧明文文件需显式设置 %s=1）"
                      % (code_l, dpaths.ALLOW_LEGACY_CRED_ENV), file=sys.stderr)
            return 2
    else:
        if a.password_stdin:
            blob = sys.stdin.read()
            try:
                d = json.loads(blob)
                email, password = d.get("email", email), d.get("password")
            except Exception:                                       # noqa: BLE001
                password = blob.strip()
        elif a.password is not None:
            password = a.password
        elif sys.stdin.isatty():
            if not email:
                email = input("email: ").strip()
            password = getpass.getpass("password: ")
    if not email or not password:
        print("缺少 email/password：用 --email + (--password | --password-stdin | --from-legacy)", file=sys.stderr)
        return 2
    ok, src, msg = DanielCredentialStore().set(email, password)
    print(json.dumps({"ok": ok, "source": src, "message": msg,
                      "email_masked": mask_email(email)}, ensure_ascii=False, indent=1))
    return 0 if ok else 3


def _cmd_delete(a):
    ok, msg = DanielCredentialStore().delete()
    print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daniel Copilot 凭据存储（TICKET-144）")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("store-status", help="显示凭据来源与各项可用性（不回显密码）").set_defaults(fn=_cmd_status)
    g = sub.add_parser("store-get", help="只回是否存在/来源（不回显密码）")
    g.set_defaults(fn=_cmd_get)
    s = sub.add_parser("store-set", help="写入系统钥匙串（失败时按需显式降级）")
    s.add_argument("--email")
    s.add_argument("--password")
    s.add_argument("--password-stdin", action="store_true",
                   help="从 stdin 读密码（或读 {\"email\":…,\"password\":…} JSON）")
    s.add_argument("--from-legacy", action="store_true",
                   help="把旧明文文件 %s 迁入钥匙串（内容不经终端回显；"
                        "该落点默认被判拒读，需先设置 %s=1）"
                        % (legacy_cred_declared(), dpaths.ALLOW_LEGACY_CRED_ENV))
    s.set_defaults(fn=_cmd_set)
    sub.add_parser("store-delete", help="删除钥匙串条目").set_defaults(fn=_cmd_delete)
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
