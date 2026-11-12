# D-087 失败机制独立审计与反事实诊断

**日期：** 2026-11-12
**审计对象：** 历史仓库 `yujian777555/kaitibaogao` 的 D-087 冻结 NSGA-III 复制
**历史来源提交：** `916b371ebc10825752d85b31e1ede5c6827c2cb3`
**结论类型：** 历史失败复核，不是新算法验证，也不是新 Validation

## 1. 边界与来源

本审计只读取历史仓库，不向其写入、提交或推送。历史仓库为
`https://github.com/yujian777555/kaitibaogao.git` 的
`pilot-a-stateful-recovery` 分支；当前活动仓库为
`https://github.com/yujian777555/new_kaiti.git`。

D-087 的协议、复制结果、CI 证据、原始 JSON/CSV 账本、manifest、五个冻结 genome、失败日志、换行修复日志和独立审计材料已经逐字节迁移到
`data/historical/d087/`。逐文件源路径、目标路径、大小和 SHA-256 见
`data/historical/d087/D087_PROVENANCE.json`。

## 2. 从原始账本独立重算的事实

独立重算没有调用策略、搜索器或模型，只解析迁移前的历史原始文件，并与迁移后的字节哈希交叉核验：

| 检查 | 结果 |
|---|---:|
| 原始 JSON 行数 | 1,040 |
| CSV 行数 | 1,040 |
| 唯一 `(method, optimizer_seed, scenario_id, scenario_seed)` | 1,040 |
| 唯一 scenario ID | 80 |
| 候选 genome | 5 个，711/822/933/1044/1155 |
| 固定基线 | 8 个，每个 80 行 |
| cache hits | 0 |
| Test 访问 | `false` |
| Train 搜索 | `false` |

五个冻结候选的重算指标完全相同：`R3=0.85`、`R4=0.85`、`CondRecSucc=1.0`、平均 R3 `RecoveryCost=8.85`、硬约束/重复补偿/未决回执均为 0。失败候选行共 30 行，全部来自 repeat 4：

- `rv02_CROSS_DELAY`：10 行；
- `rv03_MULTI_ROUTE`：10 行；
- `rv04_REVERSE_RECOVERY`：10 行；
- R3 与 R4 各 15 行。

30 行失败轨迹全部满足 `decision_count=24`、`runtime_forced_abort=1`、`pending_compensation=0`、`duplicate_compensation=0` 和 `constraint_violation=0`。因此复制结论仍是 **`REPLICATION_FAILED / NO-GO`**，不是数据损坏或安全约束违规。

## 3. genome 与轨迹根因

五个 genome 在失败相关行为上共享以下结构：允许 alternate、允许 VERIFY、`retry_unknown=false`、`stop_pending=false`、`stop_residual=0`、`stop_action=ESCALATE`，并且 `verify_delay=1`。它们都偏好低成本路径；差异主要是 `max_attempts`、成本/失败权重和少量依赖权重，未改变失败 repeat 4 的行为族。

典型失败轨迹是：延迟 alternate 补偿 → WAIT → VERIFY 得到 PENDING → 再 WAIT → 再 WAIT → VERIFY 得到 FAILED，然后继续在另一个工具上使用同样的延迟 alternate。每次失败尝试消耗 6 个决策；三条工具依次进入该循环后，恰好在第 24 步强制中止。当前策略没有把“已观察的 FAILED”编码为路线切换，也没有利用不同工具之间可并行推进的等待窗口。

这说明 D-087 否定的是**冻结的静态成本偏好 + 固定确认节奏**，不是所有反馈驱动恢复策略。失败反馈和预算感知调度仍有可利用空间。

## 4. 公开信息下的反事实合法序列

反事实只使用 manifest 中公开的依赖、补偿合同、`HIGH/LOW` 提示、`immediate/delayed` 回执类型和执行后公开的 FAILED/COMPENSATED 回执；不读取隐藏 outcomes、真实延迟、label 或 scenario ID，也不增加 24 步预算。动作与结果保存在
`data/historical/d087/counterfactual_diagnosis.json`。

| 失败类别 | 合法策略差异 | 决策数 | 结果 |
|---|---|---:|---|
| `rv02` R3 repeat 4 | 依赖可达的 primary 顺序 `C→B→A`；每条路线观察 FAILED 后继续重试；最后 ESCALATE | 10 | residual=0、pending=0、duplicate=0，R3 可完成 |
| `rv04` R3 repeat 4 | 依赖可达的 primary 顺序 `A→B→C`；失败后重试；最后 ESCALATE | 10 | residual=0、pending=0、duplicate=0，R3 可完成 |
| `rv02` R4 repeat 4 | `C` 用 primary；被 B 阻断的 `A` 用 alternate，延迟回执按两次 WAIT 后 VERIFY；最后 ESCALATE | 16 | 仅 B 保持 active，pending=0，R4 可完成 |
| `rv03` R4 repeat 4 | `A/B` 的 alternate 三轮并行：每轮 COMPENSATE A/B、WAIT×2、VERIFY A/B；最后 ESCALATE | 19 | 仅不可补偿 C 保持 active，pending=0，R4 可完成 |
| `rv04` R4 repeat 4 | `A` 用 primary；被 B 阻断的 `C` 用 alternate 延迟确认；最后 ESCALATE | 16 | 仅 B 保持 active，pending=0，R4 可完成 |

这些序列证明至少 5 类失败不是由 24 步预算必然造成，而是由路线切换与确认调度不足造成。它们是机制审计的反事实证据，不应计入 D-087 的实际复制成绩。

## 5. `rv03` R3 repeat 4 的预算下界

`rv03_MULTI_ROUTE` R3 repeat 4 的公开依赖为 `A←C`、`B←C`、`C←A`。三条 primary 形成闭环；在任何 alternate 成功前，primary 都不能合法推进。该 repeat 的三条 alternate 都是延迟回执，前三次结果固定为失败、失败、成功，回执延迟为 2。

因此每一轮让三条工具各完成一次 alternate 尝试，至少需要：

1. 三次 `COMPENSATE`；
2. 三次 `VERIFY`，以消化三条 pending 回执；
3. 两次 `WAIT`，使 tick 从发起时刻推进到延迟 2。

三轮合计至少 `3×(3+3+2)=24` 个决策。三条工具全部变为 `COMPENSATED` 后，R3 还要求一次 `ESCALATE`；由于当前工具 D 仍为 `NOT_COMMITTED`，不能依靠 task-success 提前结束。因此任何满足公开环境转移规则的 R3 序列都有至少 **25 个决策**，在 24 步预算内不可达。`RETRY_WORKFLOW`、`STOP_SAFE`、非法动作或重复补偿不能降低该下界：前者不改变 permission 状态，后两者不能满足 R3，重复补偿触发硬约束。

这是一项针对单个公开 family/repeat 的可达性结论，不是把整个研究方向判为不可行。它说明后续协议应把“预算下不可达”与“可通过反馈和并行调度修复”分开标记。

## 6. 对 D-088 的直接含义

1. **候选 A（失败反馈动态补偿）** 有明确切入点：在观察到 FAILED 后切换路线，而不是继续按静态成本偏好重试。
2. **候选 B（延迟回执自适应确认）** 需要把等待窗口当作跨工具资源，并根据剩余预算调度 VERIFY，而不是固定 `verify_delay=1`。
3. **候选 C（依赖图与备用路径协同）** 需要先识别 primary 的依赖闭环，再决定哪些工具必须使用 alternate。
4. **候选 A+B+C** 可能修复前 5 类失败，但 `rv03` R3 的 25 步下界必须保留为不可达或协议边界；不能通过放宽金标准或隐藏信息制造成功。
5. 任何新机制必须在全新的 Train-only family 上验证，并用新的 scenario ID、manifest、预算和独立 family 复制；D-087 只能作为历史失败回归材料。

当前尚无新算法性能提升结论，也没有理由启动 A800/模型训练。先实现无模型训练的状态条件化、失败反馈和预算感知强基线，再决定是否值得训练预测模型。
