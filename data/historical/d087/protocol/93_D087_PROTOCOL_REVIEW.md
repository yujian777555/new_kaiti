# 93 — D-087 独立复制协议审查与实现冻结补充

**日期：** 2026-11-12
**审查基线：** `0f53cf7ba0f1d173ae93fe5ea3d0f96d6d6ba0ff`
**结论：** **ACCEPTED_WITH_OPERATIONAL_CLARIFICATION**；只有补齐实现参数并锁定新 manifest 后才允许执行
**不改变：** 92 号原文、候选、主要终点、基线、seeds、预算和停止规则

## 1. 审查对象

完整复核 `92_D086_INDEPENDENT_VALIDATION_PREREGISTRATION.md`、90 号演化预注册、91 号探索报告、`nsga3_candidate_assessment.json`、D-086 config、原始运行记录、manifest/lock、选中指标和 CI 证据。接管时远端 main 与工作分支未漂移，ahead 275 / behind 0，工作区干净。

## 2. 候选冻结核验

直接从 `d086_experiment_runs.json` 读取 `arm=NSGA-III` 的五个 `selection.genome`，不重新调用搜索或 Pareto 选择。每个 genome 均存在于对应 archive，且对应原始 Validation 账本可按指纹找到。

- 原实验结果提交：`5210d1c40fbb41b39a51e2ef7ef544e582dc4af5`。
- 原 runs SHA-256：`5eaaa935a6e7a652a011c2f9da20362d1ddd21a192b77ae4b4980d4db50dbc06`。
- 原 config SHA-256：`4af3ac953a5610a476344bca90e4ac7f9995eac871610e02809e54976e819adc`。
- 原 manifest SHA-256：`362e7a8a0acafbb40f6ddccf207bede85a656193c6544bf3cd949c1fe43ffd67`。
- 原评估的全部探索性候选判据为 true；这不是新的算法创新证据。

候选指纹 SHA（`repr(sorted(genome.items()))`）：

| Seed | SHA-256 |
|---:|---|
| 711 | `a224de1c514ad0e9e109a47b5357443dfd6bda84bbcd93ed2e304ea7fa84e1e5` |
| 822 | `5da139f1b7e8a6cd31daf3e691f0c3833757f818fcb65eb64baceecbb955beab` |
| 933 | `e0c48be44cc36930e95ab0f60a97c19d8a40225f423a40b85bc3d459623284b2` |
| 1044 | `efd236f0c04b93abc688763d168b45bbeb1c5f65dae2f763947bcc50d843ddf2` |
| 1155 | `424f1ca40ac35056e266507208531d59b2e1bda629b408bdecb8eb6369e558d8` |

D-086 原配置、候选选择代码和结果在接管时无差异。复制过程只构造 `RecoveryGenome(**已保存字段)`，不允许重新采样、修改字段、增加 seed 或重跑 Train。

## 3. 协议审查十项

| 项 | 结论 |
|---|---|
| 候选是否冻结 | PASS；来自原 runs 的五个选中 genome |
| 配置与 SHA | PASS；原 config/runs/manifest 哈希已独立读取 |
| 原 Train 可重建性 | PASS；候选在 archive 与原始 Validation 账本中可定位，不需要重跑搜索 |
| 新 family 独立性 | 设计上为 rv01–rv04 新 ID/图/seed；须由新 manifest 验证无交叉 |
| family 泄漏 | 新评估不向策略暴露 family、scenario ID、label、隐藏 schedule 或真实延迟 |
| Validation 选择 | 原 Validation 已完成一次性选择；复制只评价已选 genome，不再选择候选 |
| 主要终点 | PASS；R3、R4、CondRecSucc、成本、硬约束及辅助指标均预注册 |
| 统计分析 | PASS；描述性逐 seed/family 结果，不新增确认性检验或事后置信区间 |
| 预算 | PASS；候选最多 400 episodes，八个固定基线共最多 640，总计最多 1,040，每 episode 24 决策 |
| Test 路径 | PASS；复制运行器不得包含 Test loader、Test namespace 或 Test 结果访问 |

## 4. 需要补齐的实现参数

92 号已固定四种新图、五种 repeat 类型、所有终点和预算，但没有逐项给出每个工具的成本、可靠性结果表和具体回执延迟。为避免执行者自由挑选有利场景，补充以下实现冻结规则；它们在任何复制结果产生前写入，不能依据结果修改。

| Family | primary 依赖（A/B/C） | primary/alternate 成本 | alternate 延迟规则 |
|---|---|---:|---|
| rv01_PARALLEL_ALT | A←C、B←A、C 无 | 4 / 1 | 全即时；primary repeat 3/4 分别延迟 1/2 |
| rv02_CROSS_DELAY | A←B、B←C、C 无 | 3 / 1 | primary 全即时；alternate repeat 3/4 分别延迟 1/2 |
| rv03_MULTI_ROUTE | A←C、B←C、C←A | 3 / 1 | alternate repeat 3/4 延迟 1/2；primary repeat 4 延迟 1 |
| rv04_REVERSE_RECOVERY | A 无、B←A、C←B | 4 / 1 | primary 全即时；alternate repeat 3/4 延迟 1/2 |

primary/alternate 提示分别固定为 HIGH/LOW。repeat 0/1/2 的 primary 结果依次为 `[True]`、`[False,True]`、`[False,False,True]`；repeat 3/4 使用 `[True]`、`[False,True]`。alternate 默认 `[True]`，rv02/rv04 使用 `[True]`、`[False,True]`、`[True]`、`[False,True]`、`[False,False,True]`；rv03 为 `[True]`、`[False,True]`、`[True]`、`[False,True]`、`[False,False,True]`；rv01 全为 `[True]`。延迟回执的补偿为非幂等，重复未知成功必须计违规。R4 的不可补偿前缀固定为 rv01=C、rv02=B、rv03=C、rv04=B，不随结果改变。

上述补充只是将 92 号机制转成确定状态转移；不改变任何主要判据、阈值或比较对象。`92` 原文保持不变，新的实现 manifest、候选文件和锁必须另行计算 SHA。

## 5. 执行前与停止边界

- 新 manifest 只能包含 Validation，不包含 Train 或 Test payload。
- 候选、原 config、原 runs、算法源码和新 manifest 的 SHA 必须写入运行记录。
- 任一候选不一致、family 交叉、标签 UNKNOWN、预算增加、缓存跨 split 或额外优化都必须阻断。
- 复制结论只能是 REPLICATION_SUPPORTED、PARTIAL_REPLICATION、REPLICATION_FAILED 或 INVALID；不是新算法创新成立。

正式 A-3b、Test、Pilot B、A800/ARWM、真实 LLM API、UndoBench TEST、ThinkingBox 和 main merge 继续禁止。
