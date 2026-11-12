# Paper 1 Safe Runner Preflight

**日期：** 2026-11-12
**状态：** `PREFLIGHT_PASS` — 确定性预检全部通过，未执行任何模型/API/优化器
**实现：** `scripts/paper1_safe_runner.py`
**测试：** `tests/test_paper1_safe_runner_preflight.py`（43 项，全部通过）

## 1. 目标与范围

本阶段实现 Paper 1 演化运行的安全预检框架。所有验证均为确定性代码检查，
不涉及 Qwen3-8B/vLLM/A800 推理、付费 API 调用、EvoTool 优化器执行、
模型训练或 Test 集策略评价。

## 2. 数据加载

| Split | 数量 | 用途 | 加载时机 |
|---|---:|---|---|
| Train | 500 | 演化搜索 | 预检阶段加载 |
| Dev | 20 | 种群选择 + 最终策略选择（S_sel） | 预检阶段加载 |
| Test | 115 | 正式评价 | 策略冻结 + 用户明确授权后延迟加载 |

- 通过 `scripts/paper1_tau_bench_splits.py` 的 `load_train_dev_splits()` 读取。
- Train/Dev 独立加载，不做随机重新划分，保留原始 `task_id`。
- 跨 split ID 重叠检查：0（已验证）。
- Test 由 `load_test_after_freeze()` 守卫，需 `policy_frozen=True` + `explicit_authorization=True` 双重门控。

## 3. 演化预算

严格遵循论文 Appendix A.6 的 G=8/B=3 协议：

| 参数 | 值 | 说明 |
|---|---:|---|
| `evolve.generations` | 8 | 显式总代数 |
| `evolve.batch_size` | 3 | 每代 mini-batch |
| `evolve.epochs` | 1 | 正值（`epochs<=0` 导致提前返回） |
| 每 seed 消耗 | 24 | 8 批次 × 3 个不同 Train task |
| `evolve.log_test_eval` | False | 禁止周期性 Test 评估 |
| `evolve(test=...)` | None | 不向 evolve 传递 Test |

### Seed=42 批次计划

| Generation | Task IDs |
|---:|---|
| 1 | retail-train-0164, retail-train-0383, retail-train-0045 |
| 2 | retail-train-0156, retail-train-0053, retail-train-0072 |
| 3 | retail-train-0315, retail-train-0209, retail-train-0074 |
| 4 | retail-train-0333, retail-train-0403, retail-train-0415 |
| 5 | retail-train-0092, retail-train-0215, retail-train-0479 |
| 6 | retail-train-0059, retail-train-0368, retail-train-0163 |
| 7 | retail-train-0210, retail-train-0251, retail-train-0443 |
| 8 | retail-train-0320, retail-train-0289, retail-train-0389 |

每批次 3 个 task_id，24 个全局唯一。不同 seed 生成不同计划，同 seed 幂等。

## 4. 选择机制

- **演化阶段**：仅访问 Train（mini-batch 内 acceptance + Blamer/Mutator）。
- **种群选择**（`select_population`）：仅访问 Dev（S_sel = 20 个 Dev task）。
- **最终策略选择**（`best_policy`）：仅访问 Dev。
- 上游随机 `split_instances()` 完全不使用。
- `log_test_eval=False` 保证 evolve() 循环中无 Test 评估。
- `test=None` 保证 Test 数据不进入 evolve()。

## 5. Test 隔离

### 文件访问级拦截

`TestIsolationGuard` 拦截 `pathlib.Path.open` 和 `builtins.open`，
当路径匹配 `test.jsonl` 时抛出 `TestAccessViolation`。

验证矩阵：

| 测试 | 结果 |
|---|---|
| 拦截 `Path.open("test.jsonl")` | PASS — 抛出 TestAccessViolation |
| 拦截 `builtins.open("test.jsonl")` | PASS — 抛出 TestAccessViolation |
| 允许 `Path.open("train.jsonl")` | PASS — 正常读取 |
| 记录违规 | PASS — violations 列表捕获路径 |
| 解除拦截后可读 | PASS — disarm() 后正常 |
| 上下文管理器 | PASS — enter/exit 自动 arm/disarm |

### evolve 参数隔离

| 测试 | 结果 |
|---|---|
| `evolve()` 签名 `test` 默认值为 `None` | PASS（inspect 验证） |
| `evolve()` 源码含 `ev.epochs <= 0` 早退 | PASS（源码验证） |
| `PreflightConfig.epochs = 1 > 0` | PASS |

## 6. 数据库注入

### 注入方式

`inject_official_db()` 将 EvoTool 的 `load_db()` 替换为返回锁定官方
tau-bench Retail DB 深拷贝的 lambda。DB 源数据从
`vendor/tau_bench/tau_bench/envs/retail/data/{users,orders,products}.json`
直接读取（绕过 `tau_bench` 包的 `litellm` 依赖链）。

### DB Parity 报告

| 维度 | users | orders | products | combined |
|---|---:|---:|---:|---:|
| 计数 | 500 | 1,000 | 50 | — |
| SHA-256 | `c712a9b6...` | `db372c34...` | `b739a976...` | `ae10e8a7...` |

完整 SHA-256：
- users: `c712a9b61256070e5c0dc676645b93d6f5ec2dc8a80182fab312d9de51cd0582`
- orders: `db372c34a4226c830305cb78feefbeaf79897de300f67db4c0b8214e205d194b`
- products: `b739a976c91e39561b40e7064f8f65572978e7cbb5a72a5bf0f2bedfa6f584dc`
- combined: `ae10e8a7f23bedf88c90a528efa2d59d27cae24b5ce1f0d28768b39257bf9f0d`

### 深拷贝隔离

| 测试 | 结果 |
|---|---|
| `load_official_db()` 计数正确（500/1000/50） | PASS |
| 两次加载哈希一致 | PASS |
| 注入后 `TauBenchEnv()` DB 哈希 == 基础 DB 哈希 | PASS |
| env 实例间 DB 互不污染 | PASS |
| 基础 DB 不受 env 变异影响 | PASS |
| `load_db()` 每次返回新副本 | PASS |

## 7. Treatment 接口设计

### 三种 Treatment

| Treatment | ID | 缓存命名空间 | 进度计算 | Blamer/Mutator 输入 |
|---|---|---|---|---|
| `EVOTOOL_LEGACY` | L | `cache_L_legacy` | status=="success" 比例 | Legacy status |
| `EVOTOOL_OUTCOME_AWARE_SELECTION` | R1 | `cache_R1_outcome_aware_selection` | outcome=="completed" 比例 | Legacy status（不变） |
| `EVOTOOL_FULL_OUTCOME_AWARE` | R2 | `cache_R2_full_outcome_aware` | outcome=="completed" 比例 | operation_outcome |

### operation_outcome 与 status 的正交分离

`status` 永不被覆盖。`operation_outcome` 由 `classify_operation_outcome()` 计算：

| status | output | operation_outcome |
|---|---|---|
| success | "Error: ..." | `domain_rejection` |
| success | "Order cancelled" | `completed` |
| error | "Error: TypeError" | `execution_error` |

### Treatment 隔离报告

| 维度 | L | R1 | R2 | 隔离验证 |
|---|---|---|---|---|
| 缓存命名空间 | `cache_L_legacy` | `cache_R1_outcome_aware_selection` | `cache_R2_full_outcome_aware` | 唯一性 PASS |
| 跨 Treatment 缓存污染 | 无 | 无 | 无 | 交叉读取返回 None |
| progress 语义 | legacy | outcome-aware | outcome-aware | 数值差异已量化 |
| Blamer/Mutator 证据 | legacy | legacy | outcome-aware | 设计区分 |

示例（3 步 episode：success/ok, success/Error: x, error/Error: y）：
- L progress = 2/3 ≈ 0.667
- R2 progress = 1/3 ≈ 0.333

## 8. 预检汇总

| # | 检查项 | 结果 |
|---:|---|---|
| 1 | 500/20/115 Split 保真 | PASS |
| 2 | 8×3 批次精确（24 unique） | PASS |
| 3 | Dev-only Selection | PASS |
| 4 | Test 文件访问拦截 | PASS |
| 5 | evolve(test=None) 参数 | PASS |
| 6 | log_test_eval=False | PASS |
| 7 | 官方 DB 注入与哈希一致 | PASS |
| 8 | Episode DB 深拷贝隔离 | PASS |
| 9 | 三种 Treatment 状态和缓存隔离 | PASS |
| 10 | 预检不调用真实 LLM/API | PASS |

## 9. 严格禁止事项（已遵守）

- 未启动 Qwen3-8B / vLLM / A800。
- 未调用 DeepSeek 或其他付费 API。
- 未执行 EvoTool 真实优化。
- 未训练任何模型。
- 未读取 Test 进行策略评价。
- 未修改 Gold Actions 或数据库。
- 未宣称任何算法提升。

## 10. 后续步骤

1. 准备正式实验授权申请：模型版本、endpoint、seed、split 使用、
   批次 ID、max_steps、输出评估器、status treatment、token 预算、
   缓存命名空间、回滚方案。
2. 获得用户明确授权后，方可启动模型推理/优化器执行。
3. Test 评价需在策略冻结 + 单独授权后执行一次。

## 11. 已知限制

- 本地 Windows 环境下 `test_evotool_full_source_lock.py` 因换行符差异失败
  （Git blob SHA 对比）；CI 在 Ubuntu 上通过。这是既有问题，与本次改动无关。
- 实际数据 JSONL 文件由 `scripts/prepare_tau_bench_retail.py` 在 CI 中生成；
  本地测试使用合成数据验证框架逻辑。
- 官方 tau-bench 对话式用户模拟器/30 步交互与 EvoTool 单指令/6 步适配
  仍是不同的协议设置；需在正式实验前明确选择并标注。
