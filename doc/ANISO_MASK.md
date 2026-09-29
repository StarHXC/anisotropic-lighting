# aniso_mask — 缎面风格各向异性主高光 Mask 节点

依据 `doc/ANISO_MASK_PLAN.md` 制作的独立 SD 节点。交付 `sd/aniso_mask.sbs`
（2048² 单通道灰度 Raw 32F，独立 `aniso_mask.resources/`，不依赖旧包）。

> **这是什么**：固定光照/normal_proxy 假设下的**缎面风格宏观主高光 Mask**，
> 不是完整 BRDF、纱线仿真、自阴影、透射或局部织纹生成。

## 1. 快速使用

1. **导入**：SD 里 File → Import 选择 `sd/aniso_mask.sbs`
   （4 张贴图已 CopiedAndLinked 内嵌于 `aniso_mask.resources/`，随包走）
2. **使用**：从 Library 拖 `aniso_mask` 进任意物质图；输出为 2048² 单通道
   灰度 Raw 32F——**0 = 无高光，1 = 最大响应**，coverage 外/无效几何区为 0
3. **作为 Blend 的 mask/opacity 使用**：把输出接到外部 Blend 的 mask/opacity
   端；配色和整体叠加强度留给使用者，本节点不提供颜色输入
4. **调参顺序建议**：默认光照 → 调方向 → 调各向异性度 → 调粗糙度/宽度 →
   必要时调光照定位；颜色、整体强度和进一步图形化整形在节点外完成

## 2. 面板（3＋2，共 5 项，全部 float 滑块）

| 分组 / ID | 显示名 | 范围 / 默认 | 语义 |
|---|---|---|---|
| 01_高光形状 / `p_anisotropy` | 各向异性度 | [0,1] / 0.7 | 两轴展开差异，0 为各向同性；不是整体亮度倍率 |
| 同组 / `p_direction_deg` | 方向（织纹参考） | [0,180]° / 0° | 从 U 参考方向绕 N 右手旋转反射长轴；180° 同一轴，90° 交换长短轴 |
| 同组 / `p_roughness` | 高光粗糙度／宽度 | [0,1] / 0.5 | 越大越宽柔；艺术映射 |
| 02_光照定位 / `p_light_azimuth_deg` | 光照方位 | [-180,180]° / -56.31° | 方向光定位 |
| 同组 / `p_light_elevation_deg` | 光照仰角 | [-89,89]° / 44.15° | 同上 |

**明确告知使用者：**

- a=0 仍有普通高光，不是全黑；整体叠加强度在外部 Blend/Levels 处理
- 长轴方向以面板定义为准，不假定它永远等于真实纱线方向；
  180° 为同一轴，90° 交换长短轴
- 光照/观察假设仍影响 Mask；不承诺只靠两个材质滑块决定所有位置
- 固定沿用 v6.2 双面处理及 `normal_proxy` 观察假设，不增加相机/视向/双面
  开关；输出不是任意真实视角正确的反射
- 已删除头发式 Shift、双层参数和分段阈值；需要进一步图形化整形时在节点
  外做

## 3. 输出契约（§4.1）

- **单一灰度输出** `mask`：2048²、单通道、线性 Raw、32F；0 = 无高光，1 = 最大响应
- coverage 外及无效几何区为 0，不填白、不扩边、不做 padding
- **不做**曝光、Reinhard、sRGB 编码、自动 gamma、逐图最大值归一化或直方图
  拉伸；不要求每套灯光都出现值 1
- 文件导出可用 Raw 灰度 PNG16；数学参考用 float32 EXR 读回
- 作为 SD Blend 的 mask/opacity 使用；若进入其他引擎按数据导入，
  **不直接接 UE Anisotropy 输入冒充材质参数图**

## 4. 数学规格（§3，实现于 `sd/aniso_mask_tools/kernel.py`）

### 4.1 独立正交反射基底

```
nN = safeNormalize(frame.normal, (0,0,1), 1e-12)      N  = nN.xyz
tN = safeNormalize(tangent_u − N·dot(N,tangent_u),
                   finitePlaneFallback(N), 1e-12)     T0 = tN.xyz
bN = safeNormalize(cross(N,T0), fallback, 1e-12)      B0 = bN.xyz
hN = safeNormalize(frame.half_vector, (0,0,1), 1e-12) H  = hN.xyz
Vg = geometry_validity × tangent_validity × nN.w × tN.w × bN.w
Vh = half_validity × hN.w
```

### 4.2 方向旋转（两轴一起转）

```
theta = p_direction_deg × π/180
T = cos(theta)·T0 + sin(theta)·B0
B = −sin(theta)·T0 + cos(theta)·B0
```

### 4.3 两轴宽度

```
a = clamp(p_anisotropy, 0, 1)
r = clamp(p_roughness, 0, 1)
alpha  = 0.03 + 0.47·r²
k      = 1 + 7·a
alphaT = alpha·√k      alphaB = alpha/√k
```
a=0 两轴相同；a=1 长短轴宽度比为 8；r=0 仍有非零下限
（0.03/√8），不生成数值奇异的理想镜面。

### 4.4 归一化椭圆主瓣与遮罩

```
hn = clamp(dot(N,H),−1,1);  ht/hb 同理（T、B）
denH = max(hn, 1e-4)
q    = (ht/(alphaT·denH))² + (hb/(alphaB·denH))²
lobe = pow(2, −min(max(q,0), 80))
frontHalf = bool_to_float(hn > 0)
facing = clamp(dot(N, light), 0, 1)
M = clamp(lobe · frontHalf · facing · Vg · Vh, 0, 1)
```

q=1 是半高轮廓，形成可旋转的椭圆；q=0 主瓣值为 1。
这是本项目的**高光形状函数**，不含完整 BRDF 的 Fresnel/Smith/能量归一化，
也不包含微观织法。

## 5. 输入继承与资源独立（§4.2）

- 槽位固定：**0=position、1=normalobj、2=coverage、3=AO**
- AO 仅为复用构图器的兼容槽，**不进入新主瓣或 frame 出口的依赖**——
  验证过替换有限 AO 数据后 Mask 不变（§8.2 隔离不变量）
- 4 张贴图已复制到独立 `aniso_mask.resources/`，不依赖旧资源目录、
  原 D: 目录或临时文件
- bitmap/PP 均显式 Raw/32F/Absolute 尺寸；生产仅 2048²

## 6. 验证摘要（M0–M3 全部 PASS）

| 阶段 | 关键证据 |
|---|---|
| M0 | legacy/frameout 位级一致（max\|Δ\|=0）；灰度 float1 直通误差 6.7e-6；RGB16 低位保持；保护清单零变化 |
| M1 | M vs CPU 参考 max\|Δ\|=2.6e-6, RMSE=1.1e-7；§8.2 十项不变量全部通过 |
| M2 | 仅 5 参数可见；1 PP+4 bitmap+1 output；双实例不同参数独立求值；保存/重载持久化；2048² 默认渲染 |
| M3 | 真实资产非退化内域 max\|Δ\|=2.74e-6, RMSE=7.13e-8；Blend 接入 lerp 语义精确（三通道一致性 6e-5，低频相关 0.9987）；性能 new/old=0.999（≤1.25 门禁）；旧 lightmap 隔离位级一致；双实例隔离位级一致 |

详细报告在 `sd/validation_mask/out/m0|/m1|/m2|/m3/`。

### 6.1 已知阈值临界像素（M3 法证留痕，§8.1）

2048² 真实资产上有 **7 个像素**的 M 在 SD 引擎与 CPU 参考间不一致（最大 0.5），
全部位于对角 coverage 缝隙处：该处 dPdu∥dPdv → 交叉积 handed **理论恒 0**，
旧核心保护阈值 `step(1e-12,|handed|)`（stages.py 保护代码，计划禁改）在
float32 引擎下对此类像素无判别力——引擎侧舍入噪声落在阈值两侧即产生分歧。
这是旧 v6.2 核心的既有行为，不是新 Mask 的算法错误；计划 §8.1 明确
"旧阈值临界像素不自动白名单"，故逐项原始值留痕于
`validation_mask/out/m3/judge_m3.json` 的 `forensic` 字段（像素坐标、handed、
M 两侧值、Vg/tValid/bValid），判定收窄到非退化内域（排除 |handed|≤1e-9
临界带，全图仅 0.13% 像素）。

### 6.2 验证工具链修复记录

- `validation_mask/png16.py`：16 位 PNG 过滤器算术曾用 `& 0xFFFF`——PNG 规范
  §6 要求按**字节** mod 256，且 Sub/Average/Paeth 回溯步长应为**每整像素字节数
  bpp=通道×2**。原实现对过滤器非 0 的 16 位图（真实资产）解码全错
  （与 FreeImage 对照 99% 像素不符），而 M1 fixtures 全部 filter 0（无过滤
  算术）故未暴露。修复后 4 张资产与 FreeImage 逐字节一致（max=0.0）。
- SD 引擎求值缓存：改参数/连接后首次 `compute()` 可能复用旧缓存。验证流程
  统一采用 `$outputsize` 10→11 往返强制重编译后再求值（m2_cache 探针证明
  有效）。

## 7. 已知限制

- 固定光照/normal_proxy 假设下的缎面风格宏观主高光 Mask；**不是**完整
  BRDF、纱线仿真、自阴影、透射或局部织纹生成
- 不进入 UE Anisotropy 输入冒充材质参数图；作为 Blend mask/opacity 使用
- 双面处理为继承的艺术约定（v6.2 的 N·L≤0 翻转门控），不宣称物理布料
  背面模型

## 8. 文件分工

```
sd/
├── stages.py                    # 唯一存量代码变更：可选 frame_out 兼容出口
├── aniso_mask.sbs               # 新交付，不覆盖旧包
├── aniso_mask.resources/        # 独立资源（4 张贴图内嵌）
├── build_aniso_mask.py          # 独立入口（main guard）
├── aniso_mask_tools/
│   ├── __init__.py
│   ├── schema.py                # 5 参数、固定常量、合法域、版本与源快照
│   ├── kernel.py                # 正交反射基底、两轴宽度、椭圆主瓣
│   └── mask_builder.py          # resolver、frame 收集、新包/输出/保存
└── validation_mask/
    ├── freeze.py                # 保护清单冻结/核对
    ├── fixtures.py              # 几何 fixtures 生成
    ├── png16.py                 # 16bit PNG 严格读取器（字节序 mod-256 过滤器）
    ├── reference.py             # 独立 CPU/解析参考
    ├── judge_m0.py / judge_m1.py / judge_m3.py
    └── out/                     # 各阶段报告
doc/ANISO_MASK.md                # 本文件
```
