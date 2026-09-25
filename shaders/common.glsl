// common.glsl — 安全运算、基底构造与共享语义（被 aniso.frag / output.frag 拼接）。
// 契约：PLAN.md §4.1（安全运算）、§4.2/§4.3（差分与基底）、§7 C1–C9（可移植性硬约束）。
//
// 可移植性注意（PLAN §7）：
// - C1 不用 dFdx/dFdy；C2 不用 mat2/3/4；C3 不用 for/while；C4 不用 if/条件运算符。
// - C5 只用加减乘除、dot/cross、min/max/clamp、abs、sqrt、sin/cos、pow、mix、step。
// - 先保证全部候选合法，再选择（禁止把无分支选择当 NaN 保护）。

// ---------------------------------------------------------------- 安全归一化
// PLAN §4.1：先算长度与有效标记，再以受保护分母计算候选，最后选择有限 fallback。
// 返回：xyz = 归一化向量或 fallback；w = 有效标记（1.0 表示输入长度 > minLen）。
vec4 safeNormalize(vec3 v, vec3 fallback, float minLen) {
    float len2 = dot(v, v);
    float valid = step(minLen * minLen, len2);
    // 受保护候选：分母 max(len2, minLen^2)，保证有限（PLAN §4.1 受保护分母）。
    vec3 candidate = v * inversesqrt(max(len2, minLen * minLen));
    // mix 两侧均为合法值（PLAN §4.1）：candidate 有限，fallback 由调用方保证有限。
    vec3 out3 = mix(fallback, candidate, valid);
    return vec4(out3, valid);
}

// 标量安全除法：分母受保护，返回 (商, 有效标记)。
vec2 safeDiv(float num, float den, float eps) {
    float valid = step(eps, abs(den));
    float q = num / (sign(den) * max(abs(den), eps));
    return vec2(q, valid);
}

// ---------------------------------------------------------------- 符号/选择
// C4：无分支选择。sign 接近 0 时归 1，避免 0 手性。
float pickSign(float x) {
    return mix(1.0, sign(x), step(1e-6, abs(x)));
}

// 三模式无分支选择（mode ∈ {0,1,2}）。
float pick3(float m0, float m1, float m2, float mode) {
    float is1 = step(0.5, mode) * (1.0 - step(1.5, mode));
    float is2 = step(1.5, mode);
    return m0 * (1.0 - step(0.5, mode)) + m1 * is1 + m2 * is2;
}

// ---------------------------------------------------------------- 分段函数
// PLAN §5.3：统一展开 t=clamp((x-edge0)/max(edge1-edge0,eps),0,1); toon=t*t*(3-2t)。
// 0 <= edge0 < edge1 <= 1 由 CPU 校验器保证；这里仅做防御性分母保护。
float smoothSegment(float x, float edge0, float edge1) {
    float t = clamp((x - edge0) / max(edge1 - edge0, 1e-5), 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

// 真正硬分段：x >= threshold 输出 1（PLAN §5.3 约定等号语义）。
float hardSegment(float x, float threshold) {
    return step(threshold, x);
}

// 分段分发：mode ∈ {0=continuous, 1=smooth, 2=hard}（PLAN §5.3/§8.1）。
float segmented(float x, float mode, float edge0, float edge1, float threshold) {
    float cont = clamp(x, 0.0, 1.0);
    float smoothV = smoothSegment(x, edge0, edge1);
    float hardV = hardSegment(x, threshold);
    return pick3(cont, smoothV, hardV, mode);
}

// ---------------------------------------------------------------- sRGB 编码
// PLAN §6.2：标准分段传递函数（IEC 61966-2-1），不是 pow(color, 1/2.2)。
// 分支两侧数值均合法（C4/C5：step+mix 展开）。
float linearToSRGB(float c) {
    c = max(c, 0.0);
    float lo = c * 12.92;
    float hi = 1.055 * pow(c, 1.0 / 2.4) - 0.055;
    float useHi = step(0.0031308, c);
    return mix(lo, hi, useHi);
}
