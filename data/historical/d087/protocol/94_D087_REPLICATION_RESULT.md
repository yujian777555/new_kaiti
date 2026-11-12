# 94 — D-087 冻结 NSGA-III 候选独立复制结果

**日期：** 2026-11-12
**结论：** **REPLICATION_FAILED / NO-GO**
**科学边界：** 不修改 D-086 历史探索结果，但不支持其跨 family 泛化主张；本实验不构成新算法创新证据

## 1. 92 号协议独立审查

`93_D087_PROTOCOL_REVIEW.md` 对 92 号逐项复核后给出 **ACCEPTED_WITH_OPERATIONAL_CLARIFICATION**。原文没有逐项冻结新 family 的成本、结果表和回执延迟，因此在任何复制结果之前，以补充文件固定这些实现参数；92 原文、候选、主要终点、基线、seeds 和预算均未改变。

- 候选来自 D-086 原 `NSGA-III` 的五个 selection.genome，不从新数据重选。
- 原 runs SHA=`5eaaa935a6e7a652a011c2f9da20362d1ddd21a192b77ae4b4980d4db50dbc06`。
- 原 config SHA=`4af3ac953a5610a476344bca90e4ac7f9995eac871610e02809e54976e819adc`。
- 冻结候选 SHA=`31495e830da326778b44398a649e2614416451107fdea982530378b4abc6244c`。
- 原结果提交：`5210d1c40fbb41b39a51e2ef7ef544e582dc4af5`；算法源码哈希逐项保存。

因此 92 号在补齐执行参数后通过协议与实现审查；这不是正式 Test 或确认性实验批准。

## 2. 新 Validation 的独立性

- 新 namespace：`d086r|validation|...`；seed base=`2026112200`。
- 四个新 family：`rv01_PARALLEL_ALT`、`rv02_CROSS_DELAY`、`rv03_MULTI_ROUTE`、`rv04_REVERSE_RECOVERY`。
- 4 families × 4 strata × 5 repeats = **80 scenarios**，R1/R2/R3/R4 各 20。
- manifest SHA=`d2cdc1aa697592e2439b5a8d5dd354726d3b8dc74e4f215530f0d4c575d88ed8`。
- 与 D-086 的 scenario ID 和 family ID 均无交集；与 D-079/D-085 不共用结果。
- 只含 Validation，不含 Train/Test；不向策略公开 scenario ID、family、label、隐藏结果表或真实延迟。

## 3. 严格按冻结协议执行

评价五个冻结 genome 与全部八个预注册固定基线：`Hand/FixedPrefix/FixedPrefixForward/RuleBased/Greedy/AdaptiveProbe/CostAware/Random`。没有重新运行 NSGA-II/III、Full、Random Search、消融或 Train。

- 冻结候选：5×80=400 episodes。
- 固定基线：8×80=640 episodes。
- 总评价：**1,040 行**，1,040 次调用，1,040 个唯一 episode-equivalent，cache hits=0。
- 每 episode 24 次决策上限；未追加预算。
- 没有真实 LLM、模型训练、参数优化、Test 或其他受禁执行。

首次写出因 CSV 头未包含候选独有字段而失败，原日志保存为 `d087_failed_execution.log`；修复为字段并集。报告合并和审计 family 查询的输出错误也分别修复并记录为 `d087_failed_audit.log`。这些修复不改变任何场景、策略、指标或判据。

## 4. 主要复制结果

五个冻结候选在新 Validation 上得到完全相同的指标，未发生 seed 挑选：

| 指标 | 每个冻结候选 |
|---|---:|
| R3 CorrectEscalation | **0.8500** |
| R4 DamageContainment | **0.8500** |
| CondRecSucc | **1.0000** |
| PrefixCompensationSuccess | 0.8500 |
| 平均 R3 RecoveryCost | 8.8500 |
| 平均 AvoidableHarm | 0.1875 |
| 平均 ResidualSideEffect | 0.4375 |
| ConstraintViolation | **0** |
| Duplicate compensation | **0** |
| Pending compensation | **0** |

Greedy 的 R3 成本为 20.0。冻结候选的成本 8.85 数值上较低，**但 Greedy 自身有 1 个未决回执，且候选没有满足恢复成功主终点，不能将成本差解释为整体优势。**

全部预注册基线的结果均保留：

| 基线 | R3 | R4 | CondRecSucc | R3 成本 | 约束违规 | 未决回执 |
|---|---:|---:|---:|---:|---:|---:|
| Hand | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 0 | 0 |
| FixedPrefix | 0.1000 | 0.0000 | 1.0000 | 4.3000 | 0 | 0 |
| FixedPrefixForward | 0.1000 | 0.0000 | 1.0000 | 3.9500 | 0 | 0 |
| RuleBased | 0.5500 | 0.0000 | 1.0000 | 12.0500 | 0 | 0 |
| Greedy | 0.9000 | 0.9500 | 1.0000 | 20.0000 | 1 | 1 |
| AdaptiveProbe | 0.8500 | 0.8500 | 1.0000 | 12.6000 | 4 | 4 |
| CostAware | 0.8500 | 0.8500 | 1.0000 | 13.3000 | 2 | 2 |
| Random | 0.0000 | 0.0000 | 1.0000 | 1.7500 | 1 | 1 |

## 5. 失败机制与跨 family 差异

`d087_failure_analysis.json` 直接从原始行计算：

- 五个候选共有 **30 个失败场景结果**（5 个冻结 genome × 6）。
- 失败全部发生于 **repeat 4**；其中 R3=15、R4=15。
- `rv02_CROSS_DELAY`、`rv03_MULTI_ROUTE`、`rv04_REVERSE_RECOVERY` 各有 10 个失败；`rv01_PARALLEL_ALT` 全部成功。
- 所有失败均达到 24 次决策上限并触发 runtime forced abort；均有零 duplicate、零 pending，但留下可避免残余。
- 原因是延迟失败补偿与冻结确认节奏的组合耗尽预算，不是标签错误、隐藏信息、重复副作用或人为修改阈值。

逐 family 的 R3/R4 结果：

| Family | R3 成功 | R4 成功 | R3 可避免伤害 | R4 可避免伤害 |
|---|---:|---:|---:|---:|
| rv01_PARALLEL_ALT | 5/5 | 5/5 | 0 | 0 |
| rv02_CROSS_DELAY | 4/5 | 4/5 | 3 | 2 |
| rv03_MULTI_ROUTE | 4/5 | 4/5 | 3 | 2 |
| rv04_REVERSE_RECOVERY | 4/5 | 4/5 | 3 | 2 |

这明确显示任务分布和确认节奏对冻结策略的影响，不能仅在 rv01 上宣称泛化。

## 6. 独立统计复核

`d087_replication_audit.py` 只读原始账本，不运行策略或优化器。16 项检查全部通过：

- JSON 与 CSV 逐字段一致，轨迹可解析；
- 每个方法/seed/scenario 唯一，1,040 行完整；
- 五个冻结 genome 指纹不变，原始 runs/config 哈希不变；
- 所有基线均执行，scenario ID 与新 manifest 完全一致；
- 没有 Train 搜索、Test、缓存复用或追加预算；
- family 等权指标、候选逐 family 指标、判据和 artifact 哈希全部一致。

统计仅限描述性逐 seed/family 比较。五个冻结 genome 不是可用来夸大显著性的新训练样本；没有新增确认性检验或事后 CI。原始结果与结论完全一致，**复制失败不是数据无效**。

## 7. 最终十项回答

1. **92 号是否通过独立审查？** 通过，但需 93 号预先补齐执行参数；科学判据未改。
2. **候选是否完全冻结？** 是；五个 genome 来自原选中记录，SHA 和来源均可核验。
3. **新 Validation 是否独立？** 是；新 family、ID、seed，且不含 Train/Test。
4. **是否严格按预注册运行？** 是；输出格式/审计修复不改变评价内容或判据。
5. **R3/R4/CondRecSucc 是否复现？** CondRecSucc=1；R3=R4=0.85，未复现原来的全成功。
6. **成本优势是否复现？** 数值上 8.85<20.0，但 Greedy 有未决回执且候选恢复失败，不能据此声称整体优势。
7. **是否有硬约束违规？** 冻结候选为 0；各基线的 pending/constraint 均单独报告，没有隐藏。
8. **统计结论是什么？** 仅描述性结果，独立账本复算一致，0/5 候选通过，REPLICATION_FAILED。
9. **能否确认跨 family 优势？** **不能。当前泛化优势不被支持，应撤回原探索结果的泛化表述，而不是删除原结果。**
10. **下一阶段是否值得发展新机制？** 不能从这次失败直接推出新机制有效。先独立复核失败机制和真实任务适配性，再决定是否有新的可证伪研究假设；不得继续调 Full 或修改冻结候选。

## 8. 唯一后续任务

由独立审查会话复核本报告、93 号协议、失败分析和原始账本，决定该路线是否终止或需要新的任务假设。当前不启动新演化搜索、模型训练、正式 A-3b、Test、Pilot B、真实 LLM API、UndoBench TEST、ThinkingBox 或 main merge。

## 9. 完整回归与提交边界

本地完整回归为 **398+28=426，全部通过**，包含冻结协议、原始账本、独立复算、跨平台 canonical 哈希和 artifact 不可变性测试。复制 workflow 仅允许 `workflow_dispatch`；regression 只重新生成 Validation manifest 并审计已保存原始账本，不随普通 push 重跑评价。

提交后仍需核验真实远端 HEAD、main、ahead/behind、文件内容和 CI，不能将本报告中的历史 run 当作新提交的证据。

## 10. 跨平台 artifact 哈希修正

结果提交 `cf162756a075358767f93d56df7001949cfeaef7` 的 regression `43154910372` 曾因 artifact_hashes=false 失败，其他复制指标和判据均通过。实际原因是 raw 字节经 Git 换行规范化后变化，而 canonical 内容一致。

现已同时保存 raw SHA-256 与 canonical SHA-256，审计使用 canonical 内容（行尾统一为 LF），raw 哈希仅作生成时的字节溯源。旧 manifest 保留为 `d087_artifact_manifest.pre_canonical_hash.json`；完整失败 CI 原始日志以 `d087_ci_43154910372_failure.log.gz` 压缩保存，字节不修改。新增 CRLF/LF 等价回归。该修复不重新评价候选，不改变 REPLICATION_FAILED / NO-GO。

最终提交后必须重新核验 CI，不得把本次失败或历史成功冒充修复后的通过。

## 11. 最终 CI 证据

修复后的代码/结果提交 `9ce0df1c0dc011de4424cd0a4f3fff79adf4e87d` 的 regression run `43156190408` = **success**。日志实际执行 398+28=426 项测试；D-087 manifest、锁和原始账本的独立审计均通过，未重新运行复制评价。

Artifact `13915563618` 已下载并再次独立复算，16 项检查全部通过，复制结论仍为 **REPLICATION_FAILED / NO-GO**。完整证据见 `95_D087_CI_EVIDENCE.json`。本结论不授权新算法搜索、模型训练、Test 或其他受禁实验。
