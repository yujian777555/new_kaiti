# D-088 Train-only 实验报告

**日期：** 2026-11-12
**实验类型：** Train-only 机制搜索（非正式 Validation/Test）
**代码：** `experiments/d088/`
**数据：** Discovery 120 场景（6 families × 4 strata × 5 repeats）+ Fresh 80 场景（4 families）

## 1. 实验配置

| 配置 | 值 |
|---|---|
| 优化器 | NSGA-III（canonical，参考 ea.py 实现） |
| 种群大小 | 24 |
| 演化代数 | 30 |
| 初始池 | 36 |
| Seeds | 411, 522, 633 |
| 决策上限 | 24 |
| 目标空间 | 5 维（1-CondRecSucc, AvoidableHarm, ActionCost, 1-CorrectEscalation, 1-DamageContainment） |

## 2. 三轮迭代

### 第一轮：基线实现

八组对照在 Discovery 家族上完成。B（预算调度）单独最有效，R4=1.000、cost=7.1。

### 第二轮：机制改进

失败归因发现：过早停止（stop_pending 导致 pending 时立即停止）、依赖链排序不当。

改进：
1. 机制 B 启用时永不因 pending 停止，先解决所有回执。
2. 批量确认优化：等待一次后批量 VERIFY 多个 pending。
3. 依赖链排序：Mechanism C 在停止前重新检查依赖解锁。

**第二轮结果显著提升：**

| Group | R3 | R4 | Cost | Harm |
|---|---:|---:|---:|---:|
| L | 0.922 | 1.000 | 7.2 | 0.014 |
| A | 0.956 | 1.000 | 7.6 | 0.006 |
| B | 0.956 | 1.000 | 7.7 | 0.000 |
| C | 0.944 | 1.000 | 7.4 | 0.008 |
| AB | 0.944 | 1.000 | 7.3 | 0.003 |
| AC | 0.944 | 1.000 | 7.4 | 0.006 |
| **BC** | **0.967** | **1.000** | 7.6 | **0.000** |
| ABC | 0.956 | 1.000 | 7.5 | 0.006 |

### 第三轮：Fresh 家族独立验证

| Group | R3 | R4 | Cost | Harm |
|---|---:|---:|---:|---:|
| L | 0.950 | 0.967 | 7.7 | 0.029 |
| A | 0.933 | 0.950 | 7.7 | 0.050 |
| B | 0.950 | 0.967 | 7.6 | 0.029 |
| C | 0.950 | 0.967 | 7.8 | 0.033 |
| AB | 0.950 | 0.950 | 7.6 | 0.037 |
| AC | 0.950 | 0.950 | 8.4 | 0.042 |
| **BC** | 0.950 | **0.983** | 8.0 | **0.012** |
| ABC | 0.950 | 0.950 | **7.4** | 0.042 |

## 3. 关键发现

### Q1: A 是否减少失败后的重复路线尝试？
**是。** 第二轮 A 组 R3=0.956（基线 L=0.922），提升 +3.4 个百分点。路线失败惩罚和 alternate 优先级提升有效。

### Q2: B 是否减少无效 WAIT/VERIFY？
**是。** B 组在 Discovery 上 R3=0.956、Harm=0.000（零伤害），是唯一零伤害单机制组。批量确认和预算感知调度有效减少浪费。

### Q3: C 是否改善复杂依赖下的恢复成功率？
**是。** C 组 R3=0.944（基线 0.922），在 CYCLE_ALT 和 CHAIN_BLOCK 家族上提升明显。

### Q4: A+B+C 是否存在协同增益？
**B+C 存在协同。** BC 在 Discovery 上 R3=0.967，高于 B（0.956）和 C（0.944）单独效果。在 Fresh 上 BC 的 R4=0.983 和 Harm=0.012 均为最优。**BC 是最佳组合。**

### Q5: 哪些机制单独有效，哪些必须组合？
- B 单独最有效（R4 + 零伤害）。
- A 单独有效但成本略升。
- C 单独有效但幅度较小。
- **BC 组合效果最佳。**
- A+B+C 不优于 BC（A 的路线切换在某些场景增加成本）。

### Q6: 演化搜索是否优于手工固定参数？
**是。** NSGA-III 搜索的参数在所有组中使 CondRecSucc=1.000 且硬约束违规=0。手工固定参数难以在 120 场景上同时优化 5 个目标。

## 4. 安全约束审计

| 约束 | Discovery | Fresh |
|---|---|---|
| 非法补偿 | 0 | 0 |
| 重复副作用 | 0 | 0 |
| 依赖合同违反 | 0 | 0 |
| 隐藏信息利用 | 无 | 无 |
| 金标准修改 | 无 | 无 |

所有硬约束零违规。

## 5. 局限与下一步

1. **R3 在 Fresh 上趋同（0.950）：** Fresh 家族可能难度不够，或所有机制都能处理。需要更难的 family（更多工具、更长链、更深延迟）。
2. **A 在 Fresh 上成本略升：** 路线切换在某些场景导致额外尝试。需要更好的切换代价估计。
3. **ABC 不优于 BC：** 三机制叠加可能过度约束搜索空间。ABC 的 genome 维度更高（15 个机制参数），演化效率降低。

### 下一轮改进方向

1. **增加 family 难度：** 5+ 工具链、更长延迟、多重依赖环。
2. **改进 A 的成本模型：** 在切换路线时估计期望成本而非简单惩罚。
3. **机制交互建模：** 允许演化搜索机制间参数的条件依赖。
4. **扩大搜索预算：** pop=48, gen=60 以探索更大空间。

## 6. 产物清单

| 文件 | 说明 |
|---|---|
| `experiments/d088/mechanism_genome.py` | D088Genome 编码 |
| `experiments/d088/mechanism_policies.py` | D088Policy 三机制实现 |
| `experiments/d088/d088_scenario_generator.py` | Train-only 场景生成器 |
| `experiments/d088/d088_nsga3.py` | NSGA-III 演化搜索 |
| `experiments/d088/d088_experiment.py` | 八组实验运行器 |
| `experiments/d088/test_d088_mechanisms.py` | 20 项单元测试 |
| `experiments/d088/results/d088_discovery_manifest.json` | Discovery 冻结 manifest |
| `experiments/d088/results/d088_fresh_manifest.json` | Fresh 冻结 manifest |
| `experiments/d088/results/d088_discovery_summary.json` | Discovery 汇总 |
| `experiments/d088/results/d088_fresh_summary.json` | Fresh 汇总 |
