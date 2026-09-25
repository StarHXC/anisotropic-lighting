# SD Pixel Processor 迁移 — Stage 0 探针包

依据 `doc/SD_MIGRATION_PLAN.md`（2026-09-25 静态审核修订版）执行。**Stage 0（0A–0E）已全部完成并通过**，证据齐备待审核方裁定是否放行 Stage 1。

## Stage 0 裁定汇总（全部有实验证据，见 validation/）

| 门禁 | 核心裁定 | 证据文件 |
|---|---|---|
| 0A | 参数载体=comp graph 层（节点级只读+无注解 API；函数图 InvalidHandle）；"PP 节点面板"效果=.sbs 实例化（wrapper，Stage 1 立项） | probe_0a_report.json、probe_0a_node_param_verdict.json |
| 0B | **bitmap 直连多输入 + sample(i,0) 0 基精确对应**（corr=1.0×4）；uniform/PP输出/shuffle 作源破坏索引（禁用）；$pos 恒等无翻转；API 读回链路（compute→SDValueTexture→save）全自动 | probe_0b_final_verdict.json |
| 0C | 16-bit PNG 与 float32 TIFF 全链路逐位无损（负值/HDR/alpha 通畅）；EXR+空色彩变换=标准数值通路 | probe_0c_final_verdict.json |
| 0D | §6 全部配方 228/228 PASS（1e-4）；**vector3 componentsin 单值端口**（多连覆盖，参考插件连法本版本损坏）；基准 planeFallback step 序曾写反已修正 | probe_0d_final_verdict.json |
| 0E | 165 节点 DAG@2048²：构建 0.004s、发射 0.089s、首算 1.11s、热算 1.10s | probe_0e_final_verdict.json |

### 自动化基础设施（本轮建成）

- **桥插件**（`bridge_plugin/`，装于 sduserplugins/aniso_pp_bridge）：文件协议轮询执行探针，
  防重入+任务签名去重；执行者用 `run_probe.py`/`_dispatch.py` 派发并自动读结果。
- **API 读回**（`aniso_pp/readback.py`）：`graph.compute() → getPropertyValue → SDTexture.save(path,'')`，
  数值验证不再需要任何手动导出。
- **实证坑位**（写代码前必读）：`SDApiError.APIException` 继承 **BaseException**（except Exception 接不住）；
  int 属性注解 min/max/step 用 SDValueInt；float3 参数值需 ctypes float3；
  PowerShell 写配置带 BOM 会让 json.load 崩（utf-8-sig 兜底）；非 2 幂参数图在 PP 中会被重采样混叠（参数图一律 2 幂 + PP 同尺寸 1:1）。

## 目录

```
sd/
├── probe_0a.py … probe_0e.py   # 五个子门禁探针（SD Python 编辑器执行）
├── dump_glsl_ref.py            # GLSL/NumPy 基准（本地 Python 执行）
├── check_export.py             # 外部验收比对器（本地 Python 执行）
├── aniso_pp/                   # 共享模块（api / emitter / __init__）
└── validation/                 # 报告、fixture、manifest、证据归档
```

## 环境要求

- **SD 侧**：Adobe Substance 3D Designer 已打开并加载目标物质图（compositing graph）。
  - **模块缓存注意**：SD 会话内重复执行探针时，探针脚本会自动清除 `aniso_pp` 的
    `sys.modules` 缓存强制重读磁盘——改完 aniso_pp 代码后直接重跑探针即可，无需重启 SD。
  - **实测环境**：SD 16.0.1 + Python 3.13.9；`SDApplication.getUIMgr()` →
    `getCurrentGraph()` 是取当前图的正确链路（无 `getUI_manager` 属性）。
- **本地侧**：Python 3.12 + `imageio`（EXR 读写需 freeimage 插件，首次调用自动下载）+ `numpy`。
  - **EXR float32 关键经验**：`iio.imwrite(..., format='EXR-FI', flags=1)` —— `flags=1`（EXR_FLOAT）才是真 float32；**默认 0（EXR_DEFAULT）写出的是 half**，低位会截断（0C 自测已验证两种模式行为）。

## 执行顺序（每项通过才进下一项）

### 0A — API/参数面板/作用域/持久化/安全重建

1. SD → Python 编辑器执行：
   ```python
   exec(open(r'E:\AI_Project\Anisotropic Lighting\sd\probe_0a.py', encoding='utf-8').read())
   ```
2. 脚本自动：建 2 个 PP + 函数图 + 三层级参数（comp graph / PP 节点 / 函数图）+ 重建演练。
3. **手动**：截图参数实际出现的面板层级；拖动 `p_probe_f1` 确认滑块/clamp 生效；保存 .sbs 重开确认持久化。
4. 产出：`validation/probe_0a_report.json` + 截图。

> **0A 裁定结论（SD 16.0.1 实测）**：参数载体三级裁定——
> ① **PP 节点级**：`newProperty` 可建属性，但 `setPropertyValue` 报 `DataIsReadOnly`，且节点无 `setPropertyAnnotationValueFromId`（注解 API 仅 SDResource 层）→ 不可承载可调参数；
> ② **perpixel 函数图级**：`newProperty` 报 `InvalidHandle`（内嵌属性图不接受动态参数）→ 同样不可承载；
> ③ **comp graph 层**：float1/int/float3 注册+读回+slider 注解全部通过 → **唯一参数载体**。
> 与参考插件 `node_builder.py:844-879`（`_expose_parameters` 只在 comp graph 建参数）实证一致。函数图内经 `get_float1/get_integer1` 读同名 comp graph 参数（0D 验证数值端点）。多 PP 实例天然共享 comp graph 参数（SD 标准行为），实例级隔离如需差异化再议（wrapper/实例参数覆盖）。

### 0B — 输入槽位/采样/坐标

1. SD 执行 `probe_0b.py`（自动建 4×4 PP + 5 个常数标记源 + 打包采样输出）。
2. **手动**：导出 4×4 PP 输出（Raw/关色彩变换/非预乘）到 `validation/`。
3. 本地：`python "sd/check_export.py" --probe 0b --sd-image <导出文件>`。
4. 坐标适配（$pos→q、q→采样地址）第二轮用梯度标记图锁定。

### 0C — 数据精度/Raw/导出读回

1. 本地先跑 `python "sd/validation/selftest_0c.py"`（判定器自测，应双向通过）。
2. SD 执行 `probe_0c.py`（生成 fixture + 建 8×8 直通 PP）。
3. **手动**：把 `validation/fixture_lsb16.png` import（**Raw/关 sRGB**）接 input0 → 导出 PNG16；把 `fixture_neghdr.exr` import（**float32 保留**）→ 导出 EXR（**float32 非 half**，Straight 非预乘）。
4. 本地：`python "sd/check_export.py" --probe 0c --png16 <导出> --exr <导出>`。

### 0D — 安全数学/类型/旋转/单层高光

1. SD 执行 `probe_0d.py`（建 PP-A/PP-B 两个 2048² 数学配方图；case 表写入 manifest）。
2. 本地：`python "sd/dump_glsl_ref.py" --probe 0d`（生成 12 case 实数公式基准）。
3. **手动**：导出 PP-A/PP-B 为 EXR float32。
4. 本地：`python "sd/check_export.py" --probe 0d --sd-exr <A.exr> --sd-exr-b <B.exr>`。
5. 判定顺序（§8.2）：有限性 → 有效性精确一致 → 有效域 `max|Δ|≤1e-4、RMSE≤1e-5`。

### 0E — DAG 可执行性/成本

1. SD 执行 `probe_0e.py`（40 层深度链 + 32 扇出 + 运行期选择 @2048²）。
2. **手动**：秒表记录首次编译耗时、参数拖动后刷新表现、视图交互帧率主观评价。
3. 产出：`validation/probe_0e_report.json`（无这些实测数字不得宣称"2048² 正常实时负载"）。

## 红线（全程）

- 只在明确选定的 comp graph 创建**带 owner 标识的新副本**；不按模糊名称清理用户图。
- 不修改 `D:\SD_Project\Plugins\` 与 GLSL 侧现有文件。
- 四张主输入全按 **Raw** 处理（无 sRGB 解码/自动法线转换/隐式 resize）。
- `p_texel_u/v` 绑定位置图真实尺寸（生产 1/2048），非艺术滑块。
- 失败即停：保留原始报错与 `probe_0x_report.json` 的 `fail` 字段，不靠改阈值绕过。
- git 提交/推送仅在用户另行授权时执行。

## 证据归档

每个子门禁的 `validation/probe_0x_report.json` + `probe_0x_check.json` + 用户截图/导出文件 + 手动观测记录 = 该门禁的证据包。0A–0E 齐后汇总交审核方裁定是否放行 Stage 1。
