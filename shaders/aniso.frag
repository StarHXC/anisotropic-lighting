#version 330
// aniso.frag — 核心线性光照 pass（含独立调试模式变体，PLAN §9 / §6.1 / §8.3）。
// 契约：PLAN.md §4（逐 texel 算法）、§5（风格化光照模型）、§7（可移植性硬约束）。
//
// 可移植性（PLAN §7）：
// - C1 不用 dFdx/dFdy：显式邻域采样，步长来自输入尺寸。
// - C2 不用 mat2/3/4：TBN/旋转按向量展开。
// - C3 不用 for/while：双层高光展开为两次 specLayer 调用。
// - C4 不用 if/条件运算符：离散模式一律以编译期 define 变体表达；
//   运行期数值选择用 step/mix，且先保证全部候选合法。
// - C7 每 pass 单一 float4：RGB=线性量，A=对应有效标记。
//
// 行序约定（PLAN §3.4）：输入纹理按「首行为顶部」上传（首行落在 v=0），
// q.y 直接等于 v；屏幕侧 v_clipUV 自下而上，screenQ() 转换一次。
// 图像 Y 翻转 / 网格 V 方向 / 绿通道符号是三个独立契约项，不在此混改。

#include <common.glsl>

// ---------------------------------------------------------------- 输入
uniform sampler2D u_position;   // 16bit RGB → rgba32f；scale/bias 待契约 verified 后应用，
                                // 当前链路假设 scale=1/bias=0（bias 对差分无影响，
                                // scale 线性缩放差分幅值，归一化基底方向不变）
uniform sampler2D u_normalobj;  // 16bit RGB → rgba32f，采样后 *2-1 解码
uniform sampler2D u_mask;       // coverage，R 通道
uniform sampler2D u_ao;         // AO，R 通道
uniform sampler2D u_detailNormal; // 仅 DETAIL_MODE==1 使用；未启用时绑定 1x1 中性图

// ---------------------------------------------------------------- 光照参数
uniform vec3  u_lightDir;       // 从表面指向光源（CPU 已归一化）
uniform vec3  u_lightColor;     // 线性
uniform float u_lightIntensity;
uniform vec3  u_ambientColor;   // 线性
uniform float u_ambientIntensity;

uniform vec3  u_viewDirection;  // directional 模式（CPU 已归一化）
uniform vec3  u_cameraPosition; // perspective 模式，与 P 同空间（PLAN §3.3）

uniform float u_anisoAngle;     // 弧度，绕 +Ns 右手（PLAN §4.5）
uniform float u_anisoAmount;    // [0,1]（PLAN §5.2）

uniform float u_shift1;
uniform float u_shift2;
uniform float u_exponent1;
uniform float u_exponent2;
uniform vec3  u_spec1Color;
uniform float u_spec1Intensity;
uniform vec3  u_spec2Color;
uniform float u_spec2Intensity;
uniform float u_specEdge0;
uniform float u_specEdge1;
uniform float u_specThreshold;
uniform float u_frontK;

uniform vec3  u_diffuseColor;
uniform float u_diffuseEdge0;
uniform float u_diffuseEdge1;
uniform float u_diffuseThreshold;
uniform float u_aoStrength;
uniform float u_aoDirectLight;  // 默认 0（PLAN §5.4）

// 细节法线（PLAN §4.4；仅 DETAIL_MODE==1 生效，未启用时 CPU 传 0）
uniform float u_detailStrength;

#ifndef DETAIL_GREEN_SIGN
#define DETAIL_GREEN_SIGN 1
#endif

// ---------------------------------------------------------------- 编译期模式
// 由 gl/context.py 注入（缺省给安全值）：
// DEBUG_MODE  0=final 光照 1=coverage 2=dPdqx 3=Tuv 4=Buv 5=Ns 6=T_aniso
//             7=原始高光层 8=N·L 9=dPdqy（PLAN §8.3 必备调试量，分 pass 输出）
// VIEW_MODE   0=directional 1=perspective 2=normal_proxy（PLAN §3.3）
// DETAIL_MODE 0=off 1=ts_detail（ts 需基底 verified，CPU 契约校验）
// DETAIL_GREEN_SIGN         ±1（PLAN §4.4 绿通道符号，独立契约项）
// SPEC_MODE / DIFFUSE_MODE  0=continuous 1=smooth 2=hard（PLAN §5.3）
// ANISO_AXIS  0=Us 1=Vs（PLAN §4.5 主轴选择）
// SPEC_LAYER_INDEX          调试原始高光时选择层（0=层1 1=层2）

#ifndef DEBUG_MODE
#define DEBUG_MODE 0
#endif
#ifndef VIEW_MODE
#define VIEW_MODE 2
#endif
#ifndef DETAIL_MODE
#define DETAIL_MODE 0
#endif
#ifndef SPEC_MODE
#define SPEC_MODE 1
#endif
#ifndef DIFFUSE_MODE
#define DIFFUSE_MODE 1
#endif
#ifndef ANISO_AXIS
#define ANISO_AXIS 0
#endif
#ifndef SPEC_LAYER_INDEX
#define SPEC_LAYER_INDEX 0
#endif

uniform vec2 u_texel; // 1/W, 1/H（输入位置图实际尺寸，PLAN §3.4）

in vec2 v_clipUV;
out vec4 fragColor;

// ---------------------------------------------------------------- q 坐标
// v_clipUV 自下而上；q 左上原点、y 向下（PLAN §3.4）。转换只此一次。
vec2 screenQ() {
    return vec2(v_clipUV.x, 1.0 - v_clipUV.y);
}

// 数据图按「首行为顶部」上传 → q.y 直接对应 v，无额外翻转。
vec4 sampleData(sampler2D tex, vec2 q) {
    return texture(tex, q);
}

// ---------------------------------------------------------------- 邻域有效性
// PLAN §4.2：邻居有效 = 未越界 + 位于有效覆盖。
// （island 限制待 island ID 落地后接入；当前以 coverage 连通域候选，契约登记。）
float neighborValid(vec2 qNeighbor) {
    vec2 low = step(vec2(0.0), qNeighbor);
    vec2 high = step(qNeighbor, vec2(1.0) - u_texel);
    float inside = low.x * low.y * high.x * high.y;
    float cov = step(0.5, sampleData(u_mask, qNeighbor).r);
    return inside * cov;
}

// ---------------------------------------------------------------- 位置差分
// PLAN §4.2：中心/单边/无有效 三态的无分支实现（权重平均公式）。
// 返回：xyz = q 坐标下的位置导数；w = 该方向有效性。
vec4 derivativeQ(vec2 qCenter, vec2 dirQ) {
    vec2 qPlus = qCenter + dirQ * u_texel;
    vec2 qMinus = qCenter - dirQ * u_texel;
    vec3 P = sampleData(u_position, qCenter).xyz;
    vec3 Pplus = sampleData(u_position, qPlus).xyz;
    vec3 Pminus = sampleData(u_position, qMinus).xyz;

    // 所有候选样本数值有限（数据图保证）；有效性仅由 coverage/越界决定。
    float validPlus = neighborValid(qPlus);
    float validMinus = neighborValid(qMinus);

    vec3 dPlus = Pplus - P;   // 正向差分 (Pplus-P)/h
    vec3 dMinus = P - Pminus; // 反向差分 (P-Pminus)/h
    // h = 1 texel（q 空间）；PLAN §4.2.4：按 0/1 权重平均，分母 max(sum,1)。
    float denom = max(validPlus + validMinus, 1.0);
    vec3 weighted = (dPlus * validPlus + dMinus * validMinus) / denom;

    float valid = step(0.5, validPlus + validMinus);
    return vec4(weighted * valid, valid);
}

// ---------------------------------------------------------------- 安全归一化辅助
// 平面 fallback 参考轴：避开与 N0 近平行的固定轴（PLAN §4.1）。
vec3 planeFallback(vec3 n) {
    // |n.x|² >= |n|²/2 → n 主要沿 X → 用 Y 轴；否则用 X 轴。
    float useY = step(dot(n, n) * 0.5, n.x * n.x);
    vec3 refAxis = mix(vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0), useY);
    // +1e-6 z 保证 n 接近零时结果仍可归一化（有限 fallback）。
    return normalize(cross(n, refAxis) + vec3(0.0, 0.0, 1e-6));
}

// ---------------------------------------------------------------- 基底构造
// PLAN §4.3：原始 UV 基底，不受高光参数影响。
void buildBasis(vec3 N0, vec3 Pu, vec3 Pv, float puValid, float pvValid,
                out vec3 Tuv, out float tValid, out vec3 Buv, out float bValid) {
    vec3 TuCandidate = Pu - N0 * dot(N0, Pu);
    vec4 tuN = safeNormalize(TuCandidate, planeFallback(N0), 1e-12);
    Tuv = tuN.xyz;
    // 退化投影或导数无效 → 失效（PLAN §4.3）
    float projLen2 = dot(TuCandidate, TuCandidate);
    tValid = tuN.w * puValid * step(1e-16, projLen2);

    // handedness_source = dot(cross(N0, Tuv), Pv)；接近零标记失效（PLAN §4.3）
    float handed = dot(cross(N0, Tuv), Pv);
    float handedValid = step(1e-12, abs(handed)) * pvValid * tValid;
    float h = pickSign(handed);
    Buv = h * cross(N0, Tuv);
    bValid = handedValid;
}

// ---------------------------------------------------------------- 细节法线
// PLAN §4.4：以 (0,0,1) 为强度 0 中性值；强度 0 严格恢复 N0。
vec3 applyDetailNormal(vec3 N0, vec3 Tuv, vec3 Buv, float strength, float greenSign, vec2 q) {
    vec3 raw = sampleData(u_detailNormal, q).xyz * 2.0 - 1.0;
    raw.y *= greenSign;
    // 按强度混合并安全归一化（PLAN §4.4.2）；原始图异常走 fallback，不悄悄吞掉。
    vec3 mixed = mix(vec3(0.0, 0.0, 1.0), raw, clamp(strength, 0.0, 1.0));
    vec4 mixedN = safeNormalize(mixed, vec3(0.0, 0.0, 1.0), 1e-12);
    vec3 n = mixedN.xyz;
    // TBN 展开：Ns = normalize(Tuv*nx + Buv*ny + N0*nz)（PLAN §4.4.2）
    return normalize(Tuv * n.x + Buv * n.y + N0 * n.z);
}

// ---------------------------------------------------------------- 高光层
// PLAN §5.2：位移切线单层高光。i=1、2 各调一次（C3 不循环）。
// 返回：rgb = 该层线性高光（未乘朝光抑制）；a = 层有效标记。
vec4 specLayer(vec3 TAniso, vec3 Ns, vec3 H, float hValid, float anisoAmount,
               float shift, float exponent, vec3 color, float intensity,
               float mode, float e0, float e1, float thr) {
    // Ti = safeNormalize(T_aniso + Ns*shift, T_aniso)（PLAN §5.2）
    vec4 tiN = safeNormalize(TAniso + Ns * shift, TAniso, 1e-12);
    vec3 Ti = tiN.xyz;

    float c = clamp(dot(Ti, H), -1.0, 1.0);
    float sinTH = sqrt(max(0.0, 1.0 - c * c));
    // exponent ∈ [1,256] 由 CPU 校验；sinTH ∈ [0,1] → pow 有限
    float aniso = pow(sinTH, exponent);

    // 各向同性对照（PLAN §5.2 艺术混合）
    float iso = pow(clamp(dot(Ns, H), 0.0, 1.0), exponent);
    float raw = mix(iso, aniso, anisoAmount);

    // 分段对已合法数值选择（PLAN §5.3）
    float shaped = segmented(raw, mode, e0, e1, thr);
    return vec4(color * (shaped * intensity), hValid);
}

// ---------------------------------------------------------------- 主函数
void main() {
    vec2 q = screenQ();

    // --- 数据解码 ---
    float coverage = step(0.5, sampleData(u_mask, q).r);
    vec3 P = sampleData(u_position, q).xyz;
    vec3 N0raw = sampleData(u_normalobj, q).xyz * 2.0 - 1.0;

    vec4 n0N = safeNormalize(N0raw, planeFallback(N0raw), 1e-12);
    vec3 N0 = n0N.xyz;
    float nValid = n0N.w * coverage;

    // --- 位置差分（PLAN §4.2）---
    vec4 dPdqx = derivativeQ(q, vec2(1.0, 0.0));
    vec4 dPdqy = derivativeQ(q, vec2(0.0, 1.0));

    // --- q → 网格 UV 导数（PLAN §3.4/§4.2.5）---
    // 烘焙映射 q=(u, 1-v)（契约登记）：dPdu = dPdqx，dPdv = -dPdqy。
    vec3 dPdu = dPdqx.xyz;
    vec3 dPdv = -dPdqy.xyz;

    // --- 原始 UV 基底（PLAN §4.3）---
    vec3 Tuv, Buv;
    float tValid, bValid;
    buildBasis(N0, dPdu, dPdv, dPdqx.w, dPdqy.w, Tuv, tValid, Buv, bValid);

    // --- 最终着色法线（PLAN §4.4；DETAIL_MODE 编译期变体）---
    vec3 Ns = N0;
#if DETAIL_MODE == 1
    Ns = applyDetailNormal(N0, Tuv, Buv, u_detailStrength, float(DETAIL_GREEN_SIGN), q);
#endif

    // --- 各向异性方向（PLAN §4.5）---
    // Us = 基础 U 方向重新投影到 Ns 切平面
    vec3 UsCandidate = Tuv - Ns * dot(Ns, Tuv);
    vec4 usN = safeNormalize(UsCandidate, Tuv, 1e-12);
    vec3 Us = usN.xyz;
    float uValid = usN.w * tValid;

    // 手性从基底传递（PLAN §4.5：用保留的手性，不无条件用 cross(N,T) 代替 +V）
    float handed = dot(cross(N0, Tuv), dPdv);
    float h = pickSign(handed);
    vec3 Vs = h * cross(Ns, Us);

    // 主轴 A（ANISO_AXIS 编译期变体）
    vec3 A = Us;
#if ANISO_AXIS == 1
    A = Vs;
#endif

    // Rodrigues 简化（PLAN §4.5）：T_aniso = cos·A + sin·cross(Ns,A)
    // A、Ns 正交单位时 theta=0 保持 A，旋转后单位长度且垂直 Ns。
    float ct = cos(u_anisoAngle);
    float st = sin(u_anisoAngle);
    vec3 TAniso = ct * A + st * cross(Ns, A);
    float tAnisoValid = uValid * nValid;

    // --- 视向（PLAN §5.1；VIEW_MODE 编译期变体）---
    vec3 Vn = Ns; // normal_proxy：V=Ns，艺术近似
#if VIEW_MODE == 0
    Vn = normalize(u_viewDirection);
#endif
#if VIEW_MODE == 1
    vec4 vpN = safeNormalize(u_cameraPosition - P, vec3(0.0, 0.0, 1.0), 1e-12);
    Vn = vpN.xyz;
#endif

    // --- 半角向量（PLAN §5.1：L+V 退化时高光无效）---
    vec4 hN = safeNormalize(u_lightDir + Vn, vec3(0.0, 0.0, 1.0), 1e-12);
    vec3 H = hN.xyz;
    float hValid = hN.w;

    // --- 双层高光（PLAN §5.2，两次展开调用）---
    vec4 s1 = specLayer(TAniso, Ns, H, hValid, u_anisoAmount,
                        u_shift1, u_exponent1, u_spec1Color, u_spec1Intensity,
                        float(SPEC_MODE), u_specEdge0, u_specEdge1, u_specThreshold);
    vec4 s2 = specLayer(TAniso, Ns, H, hValid, u_anisoAmount,
                        u_shift2, u_exponent2, u_spec2Color, u_spec2Intensity,
                        float(SPEC_MODE), u_specEdge0, u_specEdge1, u_specThreshold);

    // --- 局部朝光抑制（PLAN §5.3：frontK 有限正数）---
    float ndl = dot(Ns, u_lightDir);
    float facing = clamp(ndl * u_frontK, 0.0, 1.0);

    // 高光和乘朝光抑制与有效标记（PLAN §5.3；不称阴影可见性）
    float specValid = hValid * nValid;
    vec3 specTotal = (s1.rgb + s2.rgb) * facing * specValid;

    // --- 漫反射（PLAN §5.4：wrap 是艺术性 wrap，不是物理 Lambert）---
    float x = 0.5 * ndl + 0.5;
    float diff = segmented(x, float(DIFFUSE_MODE), u_diffuseEdge0, u_diffuseEdge1, u_diffuseThreshold);

    // --- AO（PLAN §5.4：默认只压环境项；直接影响为独立显式参数）---
    float ao = sampleData(u_ao, q).r;
    float aoFactor = mix(1.0, clamp(ao, 0.0, 1.0), u_aoStrength);
    float aoDirect = mix(1.0, aoFactor, u_aoDirectLight);

    // --- 线性合成（PLAN §5.4：环境项 + 主光·(漫反射 + 两层高光)）---
    vec3 ambient = u_ambientColor * u_ambientIntensity * aoFactor;
    vec3 direct = u_lightColor * u_lightIntensity * aoDirect
                * (u_diffuseColor * diff + specTotal);
    // 每层颜色、强度分别保存；不对已累加 HDR 提前截断（PLAN §5.4）。
    vec3 linear = ambient + direct;

    // --- 有效标记（PLAN §6.1：无效边界独立标记）---
    float validity = coverage * nValid * tValid * bValid;

    // --- 调试输出分发（DEBUG_MODE 编译期变体；C7 每 pass 单一 float4）---
#if DEBUG_MODE == 1
    fragColor = vec4(coverage, 0.0, 0.0, validity);
#elif DEBUG_MODE == 2
    fragColor = vec4(dPdqx.rgb * 0.5 + 0.5, dPdqx.w);
#elif DEBUG_MODE == 3
    fragColor = vec4(Tuv * 0.5 + 0.5, tValid);
#elif DEBUG_MODE == 4
    fragColor = vec4(Buv * 0.5 + 0.5, bValid);
#elif DEBUG_MODE == 5
    fragColor = vec4(Ns * 0.5 + 0.5, nValid);
#elif DEBUG_MODE == 6
    fragColor = vec4(TAniso * 0.5 + 0.5, tAnisoValid);
#elif DEBUG_MODE == 7
    // 原始（未分段）高光层：SPEC_LAYER_INDEX 选择层
#if SPEC_LAYER_INDEX == 1
    fragColor = vec4(s2.rgb, s2.w);
#else
    fragColor = vec4(s1.rgb, s1.w);
#endif
#elif DEBUG_MODE == 8
    fragColor = vec4(ndl * 0.5 + 0.5, 0.0, 0.0, validity);
#elif DEBUG_MODE == 9
    // 原始 q.y 位置导数（与 DEBUG_MODE 2 对称）；符号契约 dPdv=-dPdqy
    // 由基底手性检查（Buv 方向）与 GPU/CPU 逐 texel 比较共同锁定。
    fragColor = vec4(dPdqy.rgb * 0.5 + 0.5, dPdqy.w);
#else
    fragColor = vec4(linear, validity);
#endif
}
