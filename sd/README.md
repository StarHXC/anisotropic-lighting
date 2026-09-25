# SD Pixel Processor 迁移 — aniso_lightmap 交付包

Phase-2 完成：aniso.frag 主链已完整迁移进 **Substance Designer Pixel Processor**，交付 `sd/aniso_lightmap.sbs`（41 参数实时调参的自定义节点）。

> 依据 `doc/SD_MIGRATION_PLAN.md`（外部审核修订版）。Stage 0 探针 → Stage 1 主链 → Stage 2 wrapper → Stage 3 PP2 全部有数值证据，见 `validation/`。

## 快速使用

1. **导入**：SD 里 File → Import 选择 `sd/aniso_lightmap.sbs`（贴图已 CopiedAndLinked 内嵌于 `.resources/`，随包走）
2. **使用**：从 Library 拖 `aniso_lightmap` 进任意物质图；输出即成品 sRGB lightmap（2048² RGBA，A=1）
3. **调参**：选中实例 → INSTANCE PARAMETERS 面板，6 个分组 41 个滑块实时生效
4. **换资产**：重跑 `stage3_pp2.py`（改 `BAKE_ROOT` 指向新贴图目录）——图像输入无法经 Python API 创建（见「已知限制」），换资产=重新生成 wrapper

## 参数分组（41 项）

| 分组 | 内容 |
|---|---|
| 01_光照方向 | azimuth/elevation（图内角度公式生成光向）+ 强度 + 光色/环境色 |
| 02_各向异性 | 主轴 u/v、旋转角（度）、各向异性度 |
| 03_高光 | 双层 shift/exponent/颜色/强度、spec_mode、边缘阈值、front_k |
| 04_漫反射_曝光 | diffuse_mode/边缘、ao_strength/ao_direct、**exposure_ev、validity_fill**（PP2） |
| 05_观察模式 | directional/perspective/normal_proxy（int 滑块）、视向/相机 |
| 06_调试与系统 | **debug_mode 0–9**（调试视图切换）、spec_layer_index、detail（未解锁）、texel |

调试模式对照：0=成品线性 1=coverage 2=dPdqx 3=Tuv 4=Buv 5=Ns 6=TAniso 7=高光层（分段后） 8=N·L 9=dPdqy。

## 架构

```
wrapper comp graph (aniso_lightmap)
├── 41 参数（INSTANCE PARAMETERS 面板；0A 裁定的参数载体层）
├── 4 bitmap（CopiedAndLinked，显式 $outputsize=2048²/$format=32F）
├── PP1 主链（653 节点）：解码→差分→buildBasis→方向场→双层高光→漫反射/AO→linear→validity→DEBUG 级联
│   └── 函数图内 get_float1/get_integer1→tofloat/get_float3 直读 wrapper 参数
├── PP2 输出级（52 节点）：max(·,0)→2^EV→Reinhard→一次 sRGB→validityFill
└── output（setOutputNode 标记）
```

## 数值验收（全部 PASS，证据在 validation/）

| 层 | 域 | 结果 |
|---|---|---|
| 数学层（DEBUG 0–9 全模式） | 逐 texel vs GLSL dump | max\|Δ\|≤5.5e-5（阈值 1e-4） |
| 有效性 | bValid 分解对照 | 25 texel 阈值骑线（§8.2(5) 例外，RGB 零差异） |
| 成品层（PP2 sRGB 域） | vs NumPy 复算 output.frag | 99.9995% ≤2LSB；14 超差全为上述例外传导；**真实超差 0** |

## 实证坑位（SD 16.0.1 + Python 3.13.9，写 SD 自动化前必读）

- `APIException` 继承 **BaseException**——`except Exception` 接不住
- **bitmap 节点必须显式 `$outputsize`+`$format`**：SD 默认把 bitmap 缩到父图默认尺寸（256²）→ 全图插值偏差
- **`componentsin` 是单值端口**：vector2/3 多连覆盖（官方 sample 与 renderer 插件的连法在本版本损坏）；正确连法 = vector2(x→sin, y→last) → vector3(vec2→sin, z→last)
- 图像类型图输入无法经 Python API 创建（`SDTypeTexture/Usage` InvalidType）→ 贴图走 bitmap 资源直连
- comp graph 的 output 节点必须 `setOutputNode(True)`，否则实例求值 None
- 实例输出引脚 id = wrapper 输出 identifier（非 `unique_filter_output`）
- `test.compute()` 对孤立实例死码消除——外部验证必须接 output 节点
- int 参数注解 min/max/step 用 `SDValueInt`；float3 参数值需 ctypes `float3`
- samplecol 的 `int2(i,0)` 第二分量恒 0（0–4 实测无差别）
- **仅 bitmap 直连可靠**：uniform/PP输出/shuffle 作 PP 输入会破坏资源索引（多轮实验复现）
- 非幂等尺寸参数图在 PP 中被重采样混叠——参数图一律 2 幂 + PP 同尺寸 1:1
- 桥协议：探针文件名必须 `probe_<name>.py`；任务签名去重需 nonce
- imageio 写 EXR float32 必须 `flags=1`（EXR_FLOAT），默认 half

## 已知限制（明确排除项，见 PLAN 契约）

- **Unity 回贴**：不做（用户裁定）
- **边界 padding/颜色延拓**：未实现（PLAN §6.1 独立规格；两侧一致地没有）
- **同岛约束**：neighborValid 以 coverage 为候选（island ID 未落地，契约登记）
- **角度图**（anisotropic_map）与 detail_normal：参数存在但 off（资产契约 unverified）
- **位置 scale/bias**：假设 scale=1/bias=0（differential 方向不受等比缩放影响；报告留痕）
- **图像输入**：换资产需重跑生成脚本（API 缺口，见坑位）
- 参数仅 float1/int/float3；跨字段校验（edge0<edge1 等）未接入 SD 侧（本地 params.validate 可用）

## 目录

```
sd/
├── aniso_lightmap.sbs        # ★ 交付物（v3：PP1+PP2 双链）
├── aniso_pp/                 # 共享模块：api/emitter/params/readback
├── stages.py                 # 主链发射（param_resolver 双模式）
├── stage3_pp2.py             # wrapper 生成脚本（换资产时重跑）
├── bridge_plugin/            # SD 自动化桥（validation 协议）
├── dump_glsl_core.py         # GLSL 基准 dump（DEBUG 0-9）
├── check_export.py           # 外部验收比对器
└── validation/               # 全部证据：报告/裁定/基准/dump
```

## 复现判定

```powershell
# GLSL 基准（DEBUG 0-9 逐模式）
python "sd/dump_glsl_core.py"
# Stage 1/2/3 判定
python "sd/validation/_judge_dbg_matrix.py"
python "sd/validation/_judge_stage2.py"   # linear 域（Stage 1 产物）
python "sd/validation/_judge_stage3.py"   # 成品 sRGB 域（Stage 3 产物）
```
