# Phase-2 完成报告 — SD Pixel Processor 迁移

> 日期：2026-09-26
> 交付物：`sd/aniso_lightmap.sbs`（41 参数实时调参的自定义节点，双 PP 架构）
> 依据：`doc/PLAN.md`（Phase-2 手工重建 PP）+ `doc/SD_MIGRATION_PLAN.md`（外部审核修订版）
> 本文是完成状态与证据索引，供审核/交接。

---

## 1. 与 PLAN.md 契约的对照

| PLAN 条目 | 状态 | 证据 |
|---|---|---|
| §0 Phase-2「手工重建 PP 节点图」 | ✅ 以引导脚本生成同构节点图（用户已确认的交付形式），PP 双链全 API 自动搭建 | stage3_report.json |
| 步骤 3 / G2「最小 PP 对照，有效内域数值对齐」 | ✅ DEBUG 0–9 十模式逐 texel：max\|Δ\|≤5.5e-5（阈值 1e-4） | dbg_matrix_report.json、_judge_dbg_matrix.py |
| §3.4 坐标契约（q 左上原点） | ✅ SD `$pos` 恒等即 q（0B 实测无翻转） | probe_0b_final_verdict.json |
| §4.1 安全运算（safeNormalize/pickSign 等） | ✅ 0D 全配方已知答案对照 228/228 | probe_0d_final_verdict.json |
| §4.2 差分（中心/单边/无有效三态） | ✅ 逐运算复刻（含 neighborValid 四比较与 max(sum,1) 分母） | stage1_final_verdict.json |
| §4.3 buildBasis（投影+手性） | ✅ Buv 逐位对照一致；25 texel bValid 阈值骑线已定性（§8.2(5) 例外） | handed.exr、stage1_final_verdict.json |
| §5 风格化光照（双层 KK + 卡通分段 + wrap + AO） | ✅ DEBUG 7 分段后高光层对照 5.5e-5 | dbg_matrix |
| §6.2 一次输出编码（EV→Reinhard→sRGB） | ✅ PP2 逐式复刻；成品域 99.9995% ≤2LSB，真实超差 0 | stage3_final_verdict.json |
| §7 C1–C9 可移植性 | ✅ 等价达成：无 dFdx（显式邻域）、无矩阵、无循环（两次展开）、无 if（pick3/ifelse 运行期选择）、单 float4 每 pass | stages.py |
| §8.3 调试量分 pass | ✅ 单 PP 内 DEBUG 级联（运行期切换，语义与源一致） | dbg_m0..9.exr |
| §6.1 边界 padding/颜色延拓 | ⏸ 未实现（两侧一致；PLAN 归属独立规格） | — |
| 步骤 4 Unity 回贴 | ⏸ 用户裁定不做 | — |

**门禁定位**：G2（跨平台数值对齐）以 Stage 1/3 判定达成；G3 所含的 padding 与消费端验证不在本次范围（PLAN 明示为独立后续）。

## 2. 交付物使用

见 `sd/README.md`（快速使用/参数表/换资产流程/坑位清单）。

## 3. 与源实现的已知差异（全部登记，无静默改动）

1. **运行期选择替代编译期变体**：VIEW_MODE/SPEC_MODE/DEBUG_MODE 等由 `#if` 变为 pick3/ifelse 级联。全部候选常发射，数值已对照（§3.4 语义变化的验证闭环）。
2. **inversesqrt → 1/sqrt(max(len2,eps²))**：实数等价；0D 退化域单测覆盖。
3. **planeFallback +1e-6 偏置**：源有；SD 侧同式。触发诊断单列（不改 alpha）。
4. **25 texel bValid 分歧**：孔洞边缘 handed≈1e-6 骑 1e-12 阈值，两侧噪声(1e-5)下符号随机。RGB 输出零差异；成品域的 14 texel 超差即其传导。按 §8.2(5) 单列，未放宽阈值。
5. **光照方向图内生成**：azimuth/elevation → sin/cos（替代 CPU 预归一化 uniform）；单位长度数值已对照。
6. **图像输入 → bitmap 直连**：Python API 无法创建 image 图输入（实验定案）；换资产重跑脚本。

## 4. 过程资产

- **自动化**：桥插件（SD 内轮询执行探针）+ API 读回（compute→SDTexture.save）——全程零手动导出/控制台转写
- **参数化发射器**：`stages.build_core(param_resolver=…)` 双模式（常数快照/参数读取），数值一致
- **41 参数 schema**：`aniso_pp/params.py`（含跨字段校验器 validate()）
- **54 个探针脚本 + 70 份证据文件**：每项裁定可复现

## 5. 遗留与建议

1. **参数跨字段校验**：SD 侧无校验入口（非法 edge0≥edge1 会静默变形）——建议交付说明里注明合法域，或后续做 wrapper 前置判断节点
2. **换资产流程**：重跑脚本（1 分钟）；若需 UI 级换图，可评估 XML 注入 image paraminput（绕过 API 缺口，需版本兼容验证）
3. **padding**：如需边界延拓，按 PLAN §6.1 独立规格推进（两侧同步）
4. **性能**：2048² 首算 1.1s/热算 1.1s（165 节点探针实测）；主链 664 节点交互拖动流畅（参数生效实验实时返回）
