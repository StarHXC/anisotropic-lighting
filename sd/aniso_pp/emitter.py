# -*- coding: utf-8 -*-
"""SD 函数图发射器（Stage 0 / 0D 用）。

实现 doc/SD_MIGRATION_PLAN.md §5.3 类型规则（发射器内建断言）与 §6 配方表。
所有断言失败显式抛 TypeError/RuntimeError —— 不静默改线。

NodeRef.t ∈ {'f1','f2','f3','f4','bool'}。
"""
from __future__ import annotations

from sd.api.sdbasetypes import float2, float3, int2, int3
from sd.api.sdvalueint import SDValueInt
from sd.api.sdvalueint2 import SDValueInt2
from sd.api.sdvalueint3 import SDValueInt3
from sd.api.sdvaluefloat import SDValueFloat
from sd.api.sdvaluestring import SDValueString

from . import api as SDAPI

# ------------------------------------------------------------------ NodeRef

class NodeRef:
    """函数图节点引用 + 静态类型标签。t='?' 仅限 _new 内部临时态。"""
    __slots__ = ('node', 't')

    def __init__(self, node, t: str):
        assert t in ('f1', 'f2', 'f3', 'f4', 'bool', '?'), t
        self.node = node
        self.t = t

    def __repr__(self):
        return f'<NodeRef {self.t} {self.node}>'


class Emitter:
    """函数图发射器：类型断言 + 常量/广播池 + 运算方法 + §6 配方。"""

    def __init__(self, fg, *, cache_scope: str):
        self.fg = fg
        self.scope = cache_scope  # 缓存作用域（审核稿 §3.3：每个函数图独立）
        self._const_pool = {}     # (kind, t, value) -> NodeRef
        self._bcast_pool = {}     # (scope, src_node_id, target_t) -> NodeRef
        self._expr_cache = {}     # (op, 关键输入标识) -> NodeRef（仅显式登记的复合配方）
        self.node_count = 0

    # ---------------------------------------------------------- 基础发射

    def _new(self, def_id: str) -> NodeRef:
        n = self.fg.newNode(def_id)
        self.node_count += 1
        return NodeRef(n, '?')

    def _cst(self, node, value):
        n = getattr(node, 'node', node)
        n.setInputPropertyValueFromId('__constant__', value)
        return node

    # ---------------------------------------------------------- 常量与广播

    def c_f1(self, v: float) -> NodeRef:
        key = ('f1', float(v))
        if key not in self._const_pool:
            n = self._new('sbs::function::const_float1')
            self._cst(n, SDValueFloat.sNew(float(v)))
            n.t = 'f1'
            self._const_pool[key] = n
        return self._const_pool[key]

    def c_bool(self, v: bool) -> NodeRef:
        key = ('bool', bool(v))
        if key not in self._const_pool:
            n = self._new('sbs::function::const_bool')
            self._cst(n, __import__('sd.api.sdvaluebool', fromlist=['SDValueBool']).SDValueBool.sNew(bool(v)))
            n.t = 'bool'
            self._const_pool[key] = n
        return self._const_pool[key]

    def bc_f3(self, scalar: NodeRef) -> NodeRef:
        """f1 → f3 广播（同源复用；审核稿 §3.3 广播池）。

        端口语义（SD 16.0.1 实测 v3order 实验）：componentsin 只接受
        一个连接（float 或 float2），多连覆盖。标量→f3 广播走 vector2
        (sin=scl, last=scl) 得 (s,s) 再 vector3((s,s), scl)。
        """
        assert scalar.t == 'f1', scalar.t
        key = (self.scope, id(scalar.node), 'f3')
        if key not in self._bcast_pool:
            n = self._new('sbs::function::vector3')
            s2 = self._new('sbs::function::vector2')
            SDAPI.fg_connect(scalar, s2, 'componentsin')
            SDAPI.fg_connect(scalar, s2, 'componentslast')
            s2.t = 'f2'
            SDAPI.fg_connect(s2, n, 'componentsin')
            SDAPI.fg_connect(scalar, n, 'componentslast')
            n.t = 'f3'
            self._bcast_pool[key] = n
        return self._bcast_pool[key]

    # ---------------------------------------------------------- 组装
    # vector2/3/4 端口语义（v3order 实验定案）：
    #   vector2: componentsin=x(f1), componentslast=y(f1)
    #   vector3: componentsin=f1|f2, componentslast=f1|f2（合计 3 分量）
    #   vector4: componentsin=f3, componentslast=f1（推断同构，0D2 端到端验证）
    # 同一端口多连接 = 后连覆盖先连（不是数组端口）！

    def v2(self, x: NodeRef, y: NodeRef) -> NodeRef:
        assert x.t == y.t == 'f1'
        n = self._new('sbs::function::vector2')
        SDAPI.fg_connect(x, n, 'componentsin')
        SDAPI.fg_connect(y, n, 'componentslast')
        n.t = 'f2'
        return n

    def v3(self, x: NodeRef, y: NodeRef, z: NodeRef) -> NodeRef:
        assert x.t == y.t == z.t == 'f1'
        n = self._new('sbs::function::vector3')
        xy = self.v2(x, y)
        SDAPI.fg_connect(xy, n, 'componentsin')
        SDAPI.fg_connect(z, n, 'componentslast')
        n.t = 'f3'
        return n

    def v4_from_f3(self, xyz: NodeRef, w: NodeRef) -> NodeRef:
        assert xyz.t == 'f3' and w.t == 'f1'
        n = self._new('sbs::function::vector4')
        SDAPI.fg_connect(xyz, n, 'componentsin')
        SDAPI.fg_connect(w, n, 'componentslast')
        n.t = 'f4'
        return n

    def sw1(self, v: NodeRef, comp: int) -> NodeRef:
        """提取单分量。f2/f3/f4 均可。"""
        assert v.t in ('f2', 'f3', 'f4')
        n = self._new('sbs::function::swizzle1')
        SDAPI.fg_connect(v, n, 'vector')
        self._cst(n, SDValueInt.sNew(int(comp)))
        n.t = 'f1'
        return n

    # ---------------------------------------------------------- 算术（§5.3）

    def _binop(self, op_id: str, a: NodeRef, b: NodeRef, out_t: str) -> NodeRef:
        n = self._new(op_id)
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = out_t
        return n

    def add(self, a: NodeRef, b: NodeRef) -> NodeRef:
        return self._arith('sbs::function::add', a, b)

    def sub(self, a: NodeRef, b: NodeRef) -> NodeRef:
        return self._arith('sbs::function::sub', a, b)

    def mul(self, a: NodeRef, b: NodeRef) -> NodeRef:
        return self._arith('sbs::function::mul', a, b)

    def div(self, a: NodeRef, b: NodeRef) -> NodeRef:
        return self._arith('sbs::function::div', a, b)

    def _arith(self, op_id, a, b):
        """§5.3：f1×f1 原生；vecN×f1 → mulscalar；vecN±÷f1 → 广播后同型。"""
        if a.t == 'f1' and b.t == 'f1':
            return self._binop(op_id, a, b, 'f1')
        if a.t == b.t and a.t in ('f2', 'f3', 'f4'):
            return self._binop(op_id, a, b, a.t)
        # 标量与向量混合
        vec, scl = (a, b) if b.t == 'f1' else (b, a)
        assert vec.t in ('f2', 'f3', 'f4') and scl.t == 'f1', (a.t, b.t)
        if op_id == 'sbs::function::mul':
            n = self._new('sbs::function::mulscalar')
            SDAPI.fg_connect(vec, n, 'a')
            SDAPI.fg_connect(scl, n, 'scalar')
            n.t = vec.t
            return n
        if op_id == 'sbs::function::add':
            return self._binop(op_id, vec, self._bcast(vec.t, scl), vec.t)
        if op_id == 'sbs::function::sub':
            if b.t == 'f1':   # vec - scl
                return self._binop(op_id, vec, self._bcast(vec.t, scl), vec.t)
            else:             # scl - vec
                return self._binop(op_id, self._bcast(vec.t, scl), vec, vec.t)
        if op_id == 'sbs::function::div':
            if b.t == 'f1':   # vec / scl（可选 mulscalar(v,1/s)，先保护分母再优化）
                return self._binop(op_id, vec, self._bcast(vec.t, scl), vec.t)
            else:             # scl / vec → 广播后同型
                return self._binop(op_id, self._bcast(vec.t, scl), vec, vec.t)
        raise TypeError(f'不支持的混合类型运算 {op_id}: {a.t} {b.t}')

    def _bcast(self, target_t: str, scalar: NodeRef) -> NodeRef:
        if target_t == 'f2':
            return self.bc_f2(scalar)
        if target_t == 'f3':
            return self.bc_f3(scalar)
        if target_t == 'f4':
            return self.bc_f4(scalar)
        raise TypeError(target_t)

    def bc_f2(self, scalar: NodeRef) -> NodeRef:
        assert scalar.t == 'f1'
        key = (self.scope, id(scalar.node), 'f2')
        if key not in self._bcast_pool:
            n = self._new('sbs::function::vector2')
            SDAPI.fg_connect(scalar, n, 'componentsin')
            SDAPI.fg_connect(scalar, n, 'componentslast')
            n.t = 'f2'
            self._bcast_pool[key] = n
        return self._bcast_pool[key]

    def bc_f4(self, scalar: NodeRef) -> NodeRef:
        assert scalar.t == 'f1'
        key = (self.scope, id(scalar.node), 'f4')
        if key not in self._bcast_pool:
            f3 = self.bc_f3(scalar)
            n = self._new('sbs::function::vector4')
            SDAPI.fg_connect(f3, n, 'componentsin')
            SDAPI.fg_connect(scalar, n, 'componentslast')
            n.t = 'f4'
            self._bcast_pool[key] = n
        return self._bcast_pool[key]

    # ---------------------------------------------------------- 数学函数

    def sqrt(self, a: NodeRef) -> NodeRef:
        assert a.t == 'f1'
        n = self._new('sbs::function::sqrt')
        SDAPI.fg_connect(a, n, 'a')
        n.t = 'f1'
        return n

    def _unary_floor(self, a: NodeRef) -> NodeRef:
        assert a.t == 'f1'
        n = self._new('sbs::function::floor')
        SDAPI.fg_connect(a, n, 'a')
        n.t = 'f1'
        return n

    def abs_f1(self, a: NodeRef) -> NodeRef:
        assert a.t == 'f1'
        n = self._new('sbs::function::abs')
        SDAPI.fg_connect(a, n, 'a')
        n.t = 'f1'
        return n

    def pow(self, a: NodeRef, b: NodeRef) -> NodeRef:
        """§5.3：本项目 pow 只用 f1×f1。"""
        assert a.t == 'f1' and b.t == 'f1', (a.t, b.t)
        n = self._new('sbs::function::pow')
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = 'f1'
        return n

    def dot3(self, a: NodeRef, b: NodeRef) -> NodeRef:
        assert a.t == 'f3' and b.t == 'f3'
        n = self._new('sbs::function::dot')
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = 'f1'
        return n

    def sin(self, a: NodeRef) -> NodeRef:
        assert a.t == 'f1'
        n = self._new('sbs::function::sin')
        SDAPI.fg_connect(a, n, 'a')
        n.t = 'f1'
        return n

    def cos(self, a: NodeRef) -> NodeRef:
        assert a.t == 'f1'
        n = self._new('sbs::function::cos')
        SDAPI.fg_connect(a, n, 'a')
        n.t = 'f1'
        return n

    # ---------------------------------------------------------- 比较/选择

    def cmp(self, op: str, a: NodeRef, b: NodeRef) -> NodeRef:
        """比较节点：仅 f1（§5.3）；输出 bool。op ∈ gteq/gt/eq/lreq/lr/noteq。"""
        assert a.t == 'f1' and b.t == 'f1', (a.t, b.t)
        op_id = f'sbs::function::{op}'
        n = self._new(op_id)
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = 'bool'
        return n

    def sel(self, cond: NodeRef, if_true: NodeRef, if_false: NodeRef) -> NodeRef:
        """ifelse；cond 必须 bool，两路同型（不依赖短路）。"""
        assert cond.t == 'bool', cond.t
        assert if_true.t == if_false.t, (if_true.t, if_false.t)
        n = self._new('sbs::function::ifelse')
        SDAPI.fg_connect(cond, n, 'condition')
        SDAPI.fg_connect(if_true, n, 'ifpath')
        SDAPI.fg_connect(if_false, n, 'elsepath')
        n.t = if_true.t
        return n

    def bool_to_f1(self, cond: NodeRef) -> NodeRef:
        """bool → f1 掩码：SEL(cond, 1, 0)（禁止把 bool 接进数值运算）。"""
        assert cond.t == 'bool'
        return self.sel(cond, self.c_f1(1.0), self.c_f1(0.0))

    def step(self, edge: NodeRef, x: NodeRef) -> NodeRef:
        """§6：S(edge,x) = SEL(gteq(x,edge), 1, 0)；等号取 1。"""
        assert edge.t == 'f1' and x.t == 'f1'
        return self.bool_to_f1(self.cmp('gteq', x, edge))

    def lerp(self, a: NodeRef, b: NodeRef, x: NodeRef) -> NodeRef:
        """§5.3 lerp：a:fN, b:fN, x:f1 → fN。x 禁止广播（端口类型硬约束）。"""
        assert a.t == b.t, (a.t, b.t)
        assert x.t == 'f1', f'lerp.x 必须是 f1 标量, 收到 {x.t}'
        n = self._new('sbs::function::lerp')
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        SDAPI.fg_connect(x, n, 'x')
        n.t = a.t
        return n

    # ---------------------------------------------------------- §6 配方

    def safe_normalize(self, v: NodeRef, fallback: NodeRef, min_len: float) -> NodeRef:
        """safeNormalize(v, fallback, minLen) → f4(xyz=方向, w=valid)。

        §6：inversesqrt → 1/sqrt(max(len2, minLen²))；不缓存（默认）。
        v/fallback: f3。
        """
        assert v.t == 'f3' and fallback.t == 'f3'
        eps2 = self.c_f1(min_len * min_len)          # minLen 是显式语义输入
        len2 = self.dot3(v, v)
        valid = self.step(eps2, len2)                # S(eps2, len2)
        prot = self.max_f1(len2, eps2)
        inv = self.div(self.c_f1(1.0), self.sqrt(prot))
        cand = self.mulscalar(v, inv)
        out3 = self.lerp(fallback, cand, valid)      # x 是 f1
        return self.v4_from_f3(out3, valid)

    def mulscalar(self, vec: NodeRef, scalar: NodeRef) -> NodeRef:
        assert vec.t in ('f2', 'f3', 'f4') and scalar.t == 'f1'
        n = self._new('sbs::function::mulscalar')
        SDAPI.fg_connect(vec, n, 'a')
        SDAPI.fg_connect(scalar, n, 'scalar')
        n.t = vec.t
        return n

    def max_f1(self, a: NodeRef, b: NodeRef) -> NodeRef:
        assert a.t == 'f1' and b.t == 'f1'
        n = self._new('sbs::function::max')
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = 'f1'
        return n

    def min_f1(self, a: NodeRef, b: NodeRef) -> NodeRef:
        assert a.t == 'f1' and b.t == 'f1'
        n = self._new('sbs::function::min')
        SDAPI.fg_connect(a, n, 'a')
        SDAPI.fg_connect(b, n, 'b')
        n.t = 'f1'
        return n

    def plane_fallback(self, n: NodeRef) -> NodeRef:
        """§6 planeFallback(n) → f3；含 1e-6 防零偏置；cn.w 另存（触发诊断）。"""
        assert n.t == 'f3'
        nx = self.sw1(n, 0)
        ny = self.sw1(n, 1)
        len2 = self.dot3(n, n)
        use_y = self.step(self.mul(len2, self.c_f1(0.5)), self.mul(nx, nx))
        # ref = V3(1-useY, useY, 0)
        one = self.c_f1(1.0)
        ref_x = self.sub(one, use_y)
        ref = self.v3(ref_x, use_y, self.c_f1(0.0))
        # c = cross3(n, ref) + C3(0,0,1e-6)
        c = self.cross3(n, ref)
        c = self.add(c, self.v3(self.c_f1(0.0), self.c_f1(0.0), self.c_f1(1e-6)))
        cn = self.safe_normalize(c, self.v3(self.c_f1(0.0), self.c_f1(0.0), self.c_f1(1.0)), 1e-12)
        # 触发诊断：cn.w==0 表示连 fallback 都失败（单列报告，不改 core alpha）
        self._expr_cache.setdefault('planeFallback_trigger', []).append(cn)
        return self.swizzle3_from_f4(cn)

    def swizzle3_from_f4(self, v: NodeRef) -> NodeRef:
        assert v.t == 'f4'
        n = self._new('sbs::function::swizzle3')
        SDAPI.fg_connect(v, n, 'vector')
        self._cst(n, SDValueInt3.sNew(int3(0, 1, 2)))
        n.t = 'f3'
        return n

    def cross3(self, a: NodeRef, b: NodeRef) -> NodeRef:
        """§6 cross3 展开（17 节点级联已由 v3/add/sub/mul 组成）。"""
        assert a.t == 'f3' and b.t == 'f3'
        ax, ay, az = self.sw1(a, 0), self.sw1(a, 1), self.sw1(a, 2)
        bx, by, bz = self.sw1(b, 0), self.sw1(b, 1), self.sw1(b, 2)
        rx = self.sub(self.mul(ay, bz), self.mul(az, by))
        ry = self.sub(self.mul(az, bx), self.mul(ax, bz))
        rz = self.sub(self.mul(ax, by), self.mul(ay, bx))
        return self.v3(rx, ry, rz)

    def pick_sign(self, x: NodeRef) -> NodeRef:
        """§6 pickSign：|x|<1e-6 → +1；不是普通 sign。"""
        assert x.t == 'f1'
        sgn = self.sel(self.cmp('gteq', x, self.c_f1(0.0)), self.c_f1(1.0), self.c_f1(-1.0))
        return self.sel(self.cmp('gteq', self.abs_f1(x), self.c_f1(1e-6)), sgn, self.c_f1(1.0))

    def pick3(self, m0: NodeRef, m1: NodeRef, m2: NodeRef, mode: NodeRef) -> NodeRef:
        """§6 pick3：三选一（mode 来自已验证 int→float 链）。所有候选先有限。

        支持 f1 与向量两种候选类型；f1 时用 mul 而非 mulscalar。
        """
        assert m0.t == m1.t == m2.t, (m0.t, m1.t, m2.t)
        assert mode.t == 'f1'
        s05 = self.step(self.c_f1(0.5), mode)
        s15 = self.step(self.c_f1(1.5), mode)
        is1 = self.mul(s05, self.sub(self.c_f1(1.0), s15))
        is2 = s15
        w0 = self.sub(self.c_f1(1.0), s05)
        if m0.t == 'f1':
            t0 = self.mul(m0, w0)
            t1 = self.mul(m1, is1)
            t2 = self.mul(m2, is2)
        else:
            t0 = self.mulscalar(m0, w0)
            t1 = self.mulscalar(m1, is1)
            t2 = self.mulscalar(m2, is2)
        return self.add(self.add(t0, t1), t2)

    def smooth_segment(self, t: NodeRef) -> NodeRef:
        """t*t*(3-2t)，t∈[0,1] f1。"""
        t2 = self.mul(t, t)
        three_minus_2t = self.sub(self.c_f1(3.0), self.mul(self.c_f1(2.0), t))
        return self.mul(t2, three_minus_2t)

    def clamp_f1(self, x: NodeRef, lo: float, hi: float) -> NodeRef:
        """clamp(x,lo,hi) = min(max(x,lo),hi)（标量版本）。"""
        return self.min_f1(self.max_f1(x, self.c_f1(lo)), self.c_f1(hi))

    def segmented(self, x: NodeRef, mode: NodeRef, e0: NodeRef, e1: NodeRef,
                  thr: NodeRef) -> NodeRef:
        """§6 segmented：连续/平滑/硬三模式；mode f1（int 链转换后）。"""
        assert x.t == 'f1' and mode.t == 'f1'
        den = self.max_f1(self.sub(e1, e0), self.c_f1(1e-5))
        t = self.clamp_f1(self.div(self.sub(x, e0), den), 0.0, 1.0)
        smooth = self.smooth_segment(t)
        hard = self.step(thr, x)
        cont = self.clamp_f1(x, 0.0, 1.0)
        return self.pick3(cont, smooth, hard, mode)

    def linear_to_srgb_f1(self, c: NodeRef) -> NodeRef:
        """§6 linearToSRGB 每通道（IEC 61966-2-1 分段）。"""
        assert c.t == 'f1'
        cm = self.max_f1(c, self.c_f1(0.0))
        lo = self.mul(cm, self.c_f1(12.92))
        # hi = 1.055*pow(cm,1/2.4)-0.055
        hi = self.sub(self.mul(self.c_f1(1.055),
                               self.pow(cm, self.c_f1(1.0 / 2.4))),
                      self.c_f1(0.055))
        return self.sel(self.cmp('gteq', cm, self.c_f1(0.0031308)), hi, lo)
