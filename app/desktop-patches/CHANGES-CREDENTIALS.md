# CHANGES · 凭据加密存储（模型 API Key 不再明文落盘）

> 工作目录：`/tmp/dsh-build/dsh-src`
> 工具链：`export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"`
> 状态：**库内加密 + 迁移 + 单测 + 桌面构建已验；未打包、未真机启动 GUI**
> 范围：`packages/credentials/credentials-local`（`.credentials.yaml` 的读写）＋ 受影响的测试；桌面端与 `apps/` 业务代码未改。

---

## 0. 一句话

`$DSH_HOME/.credentials.yaml` 里的 API Key 与 record secret 从明文改为 `v1:` 密文；启动时把旧明文自动加密并就地覆盖（值不变、幂等）；**没有可用加密时拒绝写入**，任何路径都不会回退明文。本机 `safeStorage.isEncryptionAvailable()` 实测为 `false`，所以实际生效的是 AES-256-GCM + 0600 密钥文件；`safeStorage` 适配器保留，在能用的宿主里自动优先（§5）。

---

## 1. 改前是什么（已核实）

| 项 | 事实 |
|---|---|
| 文件 | `~/Library/Application Support/Daniel Bot/dsh-home/.credentials.yaml` |
| 权限 | `-rw-------`（0600） |
| 内容 | `refs.DEEPSEEK_API_KEY: sk-…`、`records.client-connection/browser-session.payload.secret: …` |
| 写入代码 | `packages/credentials/credentials-local/src/index.ts`：`renderRef`（旧版 L462）与 `renderRecord`（旧版 L478）把明文 YAML 直接交给 `writeFileAtomic(..., { mode: 0o600 })`；`loadInitial`（旧版 L955）读回明文 |
| 读取代码 | `parseCredentialsDocument` → `this.values` / `this.records`（旧版 L967-968），全程明文 |

也就是说：权限做到了，加密没做。任何能读该文件的进程（包括用户态恶意脚本、误传的诊断/备份）都能直接拿到 key。

---

## 2. 存储格式

每个"密"标量 = **`v1:` + base64( 1 字节 scheme + 该 scheme 的密文 )**。

| scheme 字节 | 含义 | 密文内容 |
|---|---|---|
| `1` | Electron `safeStorage` | `safeStorage.encryptString()` 的原始字节 |
| `2` | AES-256-GCM | `nonce(12) ‖ tag(16) ‖ ciphertext`，密钥 32 字节随机 |

- 仍是 `version: 1` 文档：加密是"值"层面的事，`refs` / `records` 的结构没变，旧读者遇到 `v1:` 只会当成一个普通字符串。
- 被加密的字段：
  - `refs.<NAME>` 的值；
  - `records.<scope>/<id>` 中 `kind: api-key` 的 `key` 与 `env.*`；
  - `kind: grant` 的整个 `payload`（先 `JSON.stringify` 再加密，读回解析后仍是 owner 原样的 JSON）。
- 密钥文件：**`<document>.key`**（即 `dsh-home/.credentials.yaml.key`），内容为 32 字节随机数的 base64，权限 **0600**，创建用 `wx`（并发首启不会造出两把钥匙，输家回读赢家）。
- 写入仍是 **原子写**：`writeFileAtomic(..., { mode: 0o600, dirMode: 0o700 })` + 跨进程写锁 `withFileLock`，与改动前一致。

改后的真实形状（key 已打码，只留格式）：

```yaml
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload: v1:AkdH7O…(其余打码)
refs:
  DEEPSEEK_API_KEY: v1:Ai/xOG…(其余打码)
```

---

## 3. 迁移旧明文

启动时（`Service.init` → `loadInitial`）：

1. `needsSealing()` 判定文档里是否还有明文（refs 值、api-key 的 key/env、grant 的 payload 对象）；
2. 有 → `migrateSealedDocument()` 在**写锁内**重读、重判、就地加密、原子覆盖，日志只报条数：`sealed 2 plaintext entries in …; values are unchanged`；
3. 已全密文 → **一个字节都不重写**（幂等，第二次启动文件不变）。

迁移后的值与迁移前逐字相同（解密即原文），已有单测断言：

```ts
expect(text).not.toContain('sk-migrated-one')
expect(text.match(ENVELOPE)).toHaveLength(2)
expect(await ctx.credentials.resolve(credentialRef('DSH_SEAL_ONE')))
  .toEqual({ value: 'sk-migrated-one', source: 'file' })
```

真实文件副本上的迁移实测（不改用户原文件，只测 `/tmp` 的拷贝）：

```json
{ "refValueMatchesOriginal": true, "recordSecretMatchesOriginal": true, "storedValueIsSealed": true }
{ "secondBootIdempotent": true, "secondBootResolves": true }
```

迁移失败（例如目录不可写）→ **保留原文件、`logger.warn`、不阻断启动**，该次会话继续读到明文（否则用户会凭空丢 key）。

---

## 4. 失败处理

| 场景 | 行为 | 证据 |
|---|---|---|
| 本机无任何可用加密 | `set()` 抛 `CredentialEncryptionUnavailableError`；`describe()/describeRecord()` 的 `writable` 为 `false`；**文件不动**（不写明文）。`unset()` 仍可用（删除不产生秘密） | `sealing.spec.ts` 的 "refuses writes when encryption is unavailable…" |
| `safeStorage.isEncryptionAvailable()` 为 false | 不当作"可用"：`loadSafeStorage()` 返回 `undefined`，继续尝试 0600 密钥文件；两者都不可用才拒绝写 | `sealing.ts:333`、`sealing.ts:402` |
| 密文解不开（换机、换钥匙、密文损坏） | `CredentialDecryptionError`，文案：**凭据无法解密，请重新输入 API Key**；启动失败，**不返回密文、不回退明文** | `sealing.spec.ts` 的 "fails boot with the actionable decryption error…" |
| 迁移写失败 | 保留原文件 + warn + 继续启动 | "keeps the original file and warns…" |
| 原子提交失败 | 旧文档逐字不变，`set()` 抛错 | "keeps the old document intact when an atomic commit fails" |

UI 文案就是错误 `message`（Models 页把 provider 错误原样显示）：

- 写被拒：`凭据无法加密保存：本机加密不可用（<原因>）。请修复后重试；本应用不会把 API Key 明文写入磁盘。`
- 解不开：`凭据无法解密，请重新输入 API Key（<原因>）；本机不会回退读取明文。`

> 原因串只描述"为什么"（如 `密文不是有效的 base64`、`密钥文件不可写`），**不包含任何值**。

---

## 5. `safeStorage` 在本机的真实可用性（如实）

环境：Electron **44.7.0**，`Daniel Bot.app` 与开发壳都是 **adhoc 签名**（`codesign -dv` 显示 `flags=0x2/0x20002(adhoc)`、`TeamIdentifier=not set`）。

实测三项，全部是真实输出：

1. Electron 主进程里直接问：

   ```text
   PROBE {"available":false,"roundtrip":null,"error":null,"platform":"darwin"}
   ```

   `isEncryptionAvailable()` → **false**（同一日志里 Chromium sandbox 初始化被拒、GPU/网络子进程异常退出）。

2. 真正写 `.credentials.yaml` 的进程里，根本没有 `safeStorage`：桌面端用 `ELECTRON_RUN_AS_NODE=1` 把 Host 拉成 Node 模式子进程（`apps/desktop/src/host-process.ts:212`，`node-environment.ts` 设 `ELECTRON_RUN_AS_NODE`），此模式下：

   ```text
   TYPE=string VALUE=/…/Electron.app/Contents/MacOS/Electron SAFESTORAGE=undefined
   ```

   即 `require('electron')` 只返回二进制路径，`safeStorage` 不可达。

3. 钥匙串命令行也被环境拒绝（说明这台/这个会话的钥匙串不可用，不是我们没接）：

   ```text
   security: SecKeychainItemCreateFromContent (<default>): UNIX[Operation not permitted]
   security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.
   ```

**结论**：照需求字面"`isEncryptionAvailable()` 为 false 就拒绝写"，本环境将完全无法保存 API Key（新用户连 onboarding 都过不去）。因此实现取的是**"没有任何可用加密才拒绝写"**：优先 `safeStorage`，不可用则退到 AES-256-GCM + 0600 密钥文件——**退的仍是密文，绝不退明文**。这是与需求原文唯一的偏差，明确记录在此。

**这个退路的安全边界（不吹）**：密钥文件与密文同目录；它能挡住"打开文件直接看/被备份或诊断包顺手带走/误传到聊天窗口"，挡不住"以同一用户身份运行的攻击者"（他能同时读 key 文件）。真正的强隔离需要签名后的 App + 可用钥匙串里的 `safeStorage`（或 Keychain 条目）。格式里的 scheme 字节就是为这次升级留的：届时新值写成 `scheme 1`，旧的 `scheme 2` 仍能读，不需要二次迁移。

---

## 6. 不泄漏

- 日志与错误只出现**键名/条数/文件名/原因**，从不出现值；也没有"前 6 位后 4 位"这种部分显示（代码里不存在任何截断打印）。
- YAML 解析错误只报 `code + 行/列`（`describeYamlError`），因为解析器原文会携带出错那一行（就是 secret）。
- 崩溃报告只有 stderr / 错误文本，不收集任何文件内容（`apps/desktop/src/crash-report.ts` 不遍历 `dsh-home`）；本 provider 不向 stderr 打印值，所以 `.credentials.yaml` / `.credentials.yaml.key` 的内容进不了报告。诊断包里也没有该文件的读取路径。
- 单测断言原文（`tests/sealing.spec.ts:292`）：

  ```ts
  const logged = JSON.stringify([...info.mock.calls, ...warn.mock.calls, ...error.mock.calls])
  expect(logged).not.toContain('sk-never-in-logs')
  expect(info.mock.calls.some(call => String(call[0]).includes('sealed'))).toBe(true)
  ```

---

## 7. 测试与构建证据（真实输出）

| 项 | 结果 |
|---|---|
| `packages/credentials/credentials-local` | **7 files / 120 tests passed**（新增 `tests/sealing.spec.ts` 15 条；原 105 条按"值已加密"更新断言后全绿） |
| 受影响的消费方（credentials 全家 + web-deepseek-api + web-search-deepseek + host/frontend-static + api/gateway） | **42 files / 1038 tests passed** |
| LLM 适配层（llm-deepseek + llm-pi-ai） | **49 files / 1193 tests passed** |
| `pnpm -C apps/desktop run build` | **退出码 0**（`✔ Build complete in 139ms`，vite 产物正常） |

新增 15 条覆盖：加密往返、密文前缀与 scheme 字节、密文不含明文、篡改报错、未知 scheme、`safeStorage` 路径、无加密时拒绝写、明文迁移、迁移幂等、record（api-key key/env + grant payload）加密、迁移写失败保留原文件、原子写失败不破坏旧文件、解密失败 fail boot、日志不含 key、密钥文件 0600。

---

## 8. 改动文件清单

新增：

- `packages/credentials/credentials-local/src/sealing.ts`（约 410 行：格式、两种 cipher、密钥文件、sealer 解析、错误类型）
- `packages/credentials/credentials-local/tests/sealing.spec.ts`（15 条）
- `daniel-bot/app/desktop-patches/CHANGES-CREDENTIALS.md`（本文件）

修改：

- `packages/credentials/credentials-local/src/index.ts`
  - `needsSealing` / `sealRecord` / `openRecord` / `renderSealedDocument`（L444-560）
  - `sealLegacyDocument` / `migrateSealedDocument` / `openStoredDocument`（L987-1045）
  - `renderRef` / `renderRecord` 写入即加密（L585 起）
  - `set()` 先 `assertWritable()`（L820）；`describe` / `describeRecord` 的 `writable` 取 sealer 可用性
  - `loadInitial` / `reconcileFromDisk` 读后解密
- `packages/credentials/credentials-local/tests/{local,migration,records,review-fixes}.spec.ts`（断言从"明文逐字"改为"结构不变 + `v1:` 封存 + 解密值相等"）
- `packages/credentials/deepseek-account-platform/tests/account.spec.ts`（断言 grant 落盘是密文、且不含 token 原文）

---

## 9. 没做 / 留给下一步

- **没有打包**，没有真机点 GUI（本会话无交互桌面）。
- **没能在签名后的正式包里验证 `safeStorage`**：本机只能证明"adhoc + 此环境不可用"，不能证明"签名+真机钥匙串可用"；真机验证需要在有 GUI 登录钥匙串的机器上跑一次 `isEncryptionAvailable()`。
- 桌面端的 Host 是 Node 模式子进程，即使 `safeStorage` 在主进程可用，它也**够不到**；要真正用上 `safeStorage`，需要一条 main ↔ Host 的 IPC 加密通道（或改由 main 独占凭据写入）。本次未做，故落盘实际用的是 AES-256-GCM。
