# D-088 状态条件化恢复机制设计

**日期：** 2026-11-12
**状态：** `IMPLEMENTED_AND_TESTED` — 三机制已实现、经三轮 Train-only 对照实验
**代码：** `experiments/d088/`
**环境：** D-086 DependencyRecoveryEnv（`data/historical/d087/source/dependency_recovery.py`）

## 1. 研究背景

D-087 冻结 NSGA-III 候选复制结果为 `REPLICATION_FAILED / NO-GO`。失败机制审计（docs/13）确认：
- 30 条失败全部在 repeat 4，耗尽 24 步预算。
- 五个候选共享固定确认节奏 `verify_delay=1` 和静态路线偏好。
- 观察到 FAILED 后未切换路线，跨工具等待窗口未协调。
- 5 类失败存在公开信息下的合法反事实恢复序列。

**研究判断：** D-087 否定的是冻结的静态策略，不是所有状态条件化恢复机制。

## 2. 三机制设计

### 机制 A：Failure-Feedback Route Switching

**解决问题：** 观察到 FAILED 后仍重复使用同路线。

**核心思想：** 跟踪每个 (tool, route) 的失败次数和连续尝试次数，超过阈值后排除/降权该路线；当 primary 失败后提高 alternate 优先级。

**基因参数：**

| 参数 | 类型 | 范围 | 作用 |
|---|---|---|---|
| `enable_mech_a` | bool | {True, False} | 启用开关 |
| `failure_switch_threshold` | int | 1-4 | 触发路线切换的失败次数阈值 |
| `max_consecutive_same_route` | int | 1-4 | 同路线最大连续尝试次数 |
| `alternate_priority_boost` | float | 0.0-3.0 | primary 失败后 alternate 优先级提升 |
| `route_failure_penalty` | float | -3.0-0.0 | 路线失败惩罚权重 |

### 机制 B：Delay-Aware Budget Scheduling

**解决问题：** 固定 WAIT/VERIFY 节奏，未利用跨工具并行等待窗口。

**核心思想：** 将 WAIT 视为推进多个工具回执的共享资源；批量 VERIFY；根据剩余预算动态调度；在预算耗尽前处理未决补偿。

**基因参数：**

| 参数 | 类型 | 范围 | 作用 |
|---|---|---|---|
| `enable_mech_b` | bool | {True, False} | 启用开关 |
| `budget_urgency_weight` | float | 0.0-2.0 | 预算紧迫性权重 |
| `batch_verify_threshold` | int | 1-3 | 批量确认的 pending 阈值 |
| `wait_efficiency_weight` | float | 0.0-2.0 | 跨工具等待效率权重 |
| `pre_deadline_verify_margin` | int | 0-4 | 预算耗尽前确认边距 |

**关键改进（第二轮）：** 启用机制 B 时永不因 pending 停止，先解决所有回执再决策。

### 机制 C：Dependency-Graph / Alternate-Path Coordination

**解决问题：** 复杂依赖关系下静态路线选择陷入循环或错误顺序。

**核心思想：** 构建公开依赖图；检测 primary 依赖环（SCC）；环内工具优先使用 alternate；拓扑排序调度；优先执行解锁关键依赖的动作。

**基因参数：**

| 参数 | 类型 | 范围 | 作用 |
|---|---|---|---|
| `enable_mech_c` | bool | {True, False} | 启用开关 |
| `cycle_aware_routing` | bool | {True, False} | 环检测路由 |
| `topological_order_weight` | float | 0.0-2.0 | 拓扑排序权重 |
| `dependency_unlock_priority` | float | 0.0-3.0 | 解锁依赖优先级 |

## 3. Genome 编码

`D088Genome` 继承 D-086 `RecoveryGenome`，新增 15 个机制参数。全部参数均可由 NSGA-III 演化搜索。

基础参数（继承自 RecoveryGenome）：
- `hint_weight`, `cost_weight`, `failure_weight`, `position_weight`, `dependency_weight`（连续）
- `max_attempts`, `verify_delay`, `stop_residual`（离散）
- `retry_unknown`, `stop_pending`, `allow_alternate`, `allow_verify`（布尔）
- `stop_action`（ESCALATE/STOP_SAFE）

## 4. 八组实验设计

| 实验组 | enable_a | enable_b | enable_c | 说明 |
|---|---|---|---|---|
| L | False | False | False | 原始静态机制 |
| A | True | False | False | 仅路线切换 |
| B | False | True | False | 仅预算调度 |
| C | False | False | True | 仅依赖图协调 |
| AB | True | True | False | A+B |
| AC | True | False | True | A+C |
| BC | False | True | True | B+C |
| ABC | True | True | True | 全部 |

公平性约束：相同评价预算（pop=24, gen=30）、相同决策上限（24）、相同场景和种子（411/522/633）、独立缓存、相同评价器。

## 5. 数据

### Discovery Train-only families（6 个）

| Family | 依赖拓扑 | 工具数 | 特点 |
|---|---|---|---|
| d088t_CHAIN_BLOCK | A←B←C←D 线性链 | 4+Z | 深度依赖链 |
| d088t_FORK_JOIN | A→{B,C}→D 菱形 | 4+Z | 分叉-汇合 |
| d088t_CYCLE_ALT | A←B←C←A 循环 | 3+Z | primary 依赖环 |
| d088t_PARALLEL_SINK | A,B→C 并行汇 | 3+Z | 并行等待 |
| d088t_DEEP_CHAIN | A←B←C 深链 | 3+Z | 链式阻塞 |
| d088t_STAR_HUB | A→{B,C,D} 星形 | 4+Z | 中心依赖 |

### Fresh Train-only families（4 个）

d088f_DIAMOND, d088f_LADDER, d088f_MULTI_FORK, d088f_LOOP_BREAK

所有场景 ID 使用 `d088|train|` 命名空间，与 D-086/D-087/D-079/D-085 无重叠。覆盖 R1/R2/R3/R4 四层。

## 6. 安全约束

零容忍约束（未违反）：
- 不允许非法补偿
- 不允许重复副作用
- 不允许违反依赖合同
- 不允许利用隐藏信息
- 不允许修改金标准

所有实验 `constraint_violation=0`, `duplicate_compensation=0`。
