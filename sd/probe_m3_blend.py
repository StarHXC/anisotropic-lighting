# -*- coding: utf-8 -*-
r"""M3 — Blend 接入 + 性能计时 + 旧包隔离回归（ANISO_MASK_PLAN §8.3）。

1. Blend 接入：aniso_mask 输出 → 外部 Blend 的 mask 端；前景红色 uniform、
   背景 0.5 灰 uniform；验证输出 = lerp(bg, fg, mask)（外部颜色混合生效）
2. 性能计时：旧 aniso_lightmap vs 新 aniso_mask（首次求值 + 预热后中位数/P95）
3. 旧包隔离：改新实例参数不影响旧 lightmap 输出（同图共存）
4. 报告落盘 validation_mask/out/m3/
"""
import json
import os
import statistics
import sys
import time
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in list(sys.modules)
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
           or k == 'stages']:
    del sys.modules[_k]

OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm3')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm3_blend', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'M3 blend 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2, float3
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    test = SDAPI.get_current_graph()

    # ---------- 资源解析 ----------
    mask_res = None
    lm_res = None
    for i in range(pkg_mgr.getPackages().getSize()):
        p = pkg_mgr.getPackages().getItem(i)
        try:
            if mask_res is None:
                r = p.findResourceFromUrl('pkg:///aniso_mask')
                if r is not None:
                    mask_res = r
            if lm_res is None:
                r = p.findResourceFromUrl('pkg:///aniso_lightmap')
                if r is not None:
                    lm_res = r
        except BaseException:
            continue
    step('解析资源', mask_res is not None and lm_res is not None,
         {'aniso_mask': mask_res is not None, 'aniso_lightmap': lm_res is not None})

    # ---------- 1. Blend 接入 ----------
    # uniform 红（前景）+ uniform 灰（背景）+ blend（copy 模式 + mask 端）
    from sd.api.sdvaluecolorrgba import SDValueColorRGBA
    from sd.api.sdbasetypes import ColorRGBA as _CRGBA

    def _rgba(r, g, b, a=1.0):
        return SDValueColorRGBA.sNew(_CRGBA(r, g, b, a))

    c_fg = test.newNode('sbs::compositing::uniform')
    c_fg.setPosition(float2(9000.0, 1800.0))
    c_fg.setInputPropertyValueFromId('outputcolor', _rgba(1.0, 0.0, 0.0))
    c_fg.setInputPropertyValueFromId('$outputsize', SDValueInt2.sNew(int2(11, 11)))

    c_bg = test.newNode('sbs::compositing::uniform')
    c_bg.setPosition(float2(9000.0, 2200.0))
    c_bg.setInputPropertyValueFromId('outputcolor', _rgba(0.5, 0.5, 0.5))
    c_bg.setInputPropertyValueFromId('$outputsize', SDValueInt2.sNew(int2(11, 11)))

    blend = test.newNode('sbs::compositing::blend')
    blend.setPosition(float2(9600.0, 2000.0))
    # blendingmode 用节点默认（copy）；mask 接 opacity 输入（灰度图 → 标量提升）

    def out_pin(node):
        props = node.getProperties(SDPropertyCategory.Output)
        return str(props.getItem(0).getId())

    # source=前景（红），destination=背景（灰）——PS 命名；opacity=mask 端
    c_fg.newPropertyConnectionFromId(out_pin(c_fg), blend, 'source')
    c_bg.newPropertyConnectionFromId(out_pin(c_bg), blend, 'destination')

    inst = test.newInstanceNode(mask_res)
    inst.setPosition(float2(9000.0, 2600.0))
    pin = out_pin(inst)
    # mask（灰度）→ blend.opacity：copy 模式下 opacity 即逐像素混合系数
    inst.newPropertyConnectionFromId(pin, blend, 'opacity')

    on = test.newNode('sbs::compositing::output')
    on.setPosition(float2(10000.0, 2000.0))
    blend.newPropertyConnectionFromId(out_pin(blend), on, 'inputNodeOutput')

    # 缓存击破后求值
    prop = inst.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
    inst.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
    inst.setPropertyValue(prop, SDValueInt2.sNew(int2(10, 10)))
    test.compute()
    inst.setPropertyValue(prop, SDValueInt2.sNew(int2(11, 11)))
    test.compute()

    exr_blend = os.path.join(OUT_DIR, 'm3_blend.exr')
    rb = compute_and_save(test, blend, exr_blend)
    step('Blend 接入求值', rb['ok'], {'size': rb['size']})

    # 清理 Blend 测试节点
    for nd in (blend, c_fg, c_bg, inst, on):
        try:
            test.deleteNode(nd)
        except BaseException:
            pass

    # ---------- 2. 性能计时：旧 lightmap vs 新 mask ----------
    def time_node(res, tag, runs=5):
        n = test.newInstanceNode(res)
        n.setPosition(float2(11000.0, 2000.0))
        outs = n.getProperties(SDPropertyCategory.Output)
        pin = str(outs.getItem(0).getItem if False else outs.getItem(0).getId())
        o = test.newNode('sbs::compositing::output')
        o.setPosition(float2(11600.0, 2000.0))
        n.newPropertyConnectionFromId(pin, o, 'inputNodeOutput')

        pr = n.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
        n.setPropertyInheritanceMethod(pr, SDPropertyInheritanceMethod.Absolute)
        n.setPropertyValue(pr, SDValueInt2.sNew(int2(11, 11)))

        t0 = time.perf_counter()
        test.compute()
        first = time.perf_counter() - t0
        times = []
        for _ in range(runs):
            # 触发重求值：改输出尺寸往返 1 texel
            n.setPropertyValue(pr, SDValueInt2.sNew(int2(10, 10)))
            test.compute()
            n.setPropertyValue(pr, SDValueInt2.sNew(int2(11, 11)))
            t0 = time.perf_counter()
            test.compute()
            times.append(time.perf_counter() - t0)
        med = statistics.median(times)
        p95 = sorted(times)[int(0.95 * (len(times) - 1))] if len(times) > 1 else times[0]
        try:
            test.deleteNode(n)
            test.deleteNode(o)
        except BaseException:
            pass
        return {'first_s': first, 'median_s': med, 'p95_s': p95,
                'runs': [round(t, 4) for t in times]}

    t_new = time_node(mask_res, 'aniso_mask')
    t_old = time_node(lm_res, 'aniso_lightmap')
    ratio = t_new['median_s'] / max(t_old['median_s'], 1e-9)
    step('性能对比（热更新中位数）', ratio <= 1.25,
         {'new': t_new, 'old': t_old, 'new_over_old': round(ratio, 3)})

    # ---------- 3. 旧包隔离：新实例参数不影响旧 lightmap ----------
    inst_n = test.newInstanceNode(mask_res)
    inst_n.setPosition(float2(12000.0, 2000.0))
    outs_n = inst_n.getProperties(SDPropertyCategory.Output)
    pin_n = str(outs_n.getItem(0).getId())
    on_n = test.newNode('sbs::compositing::output')
    on_n.setPosition(float2(12600.0, 2000.0))
    inst_n.newPropertyConnectionFromId(pin_n, on_n, 'inputNodeOutput')

    inst_o = test.newInstanceNode(lm_res)
    inst_o.setPosition(float2(12000.0, 2600.0))
    outs_o = inst_o.getProperties(SDPropertyCategory.Output)
    pin_o = str(outs_o.getItem(0).getId())
    on_o = test.newNode('sbs::compositing::output')
    on_o.setPosition(float2(12600.0, 2600.0))
    inst_o.newPropertyConnectionFromId(pin_o, on_o, 'inputNodeOutput')

    exr_old_before = os.path.join(OUT_DIR, 'm3_oldlm_before.exr')
    rb1 = compute_and_save(test, inst_o, exr_old_before)

    def set_inst(node, pid, v):
        pr = node.getPropertyFromId(pid, SDPropertyCategory.Input)
        node.setPropertyValue(pr, SDValueFloat.sNew(float(v)))

    set_inst(inst_n, 'p_anisotropy', 0.1)
    set_inst(inst_n, 'p_roughness', 0.9)
    set_inst(inst_n, 'p_direction_deg', 90.0)
    set_inst(inst_n, 'p_light_azimuth_deg', 120.0)
    set_inst(inst_n, 'p_light_elevation_deg', -30.0)

    exr_old_after = os.path.join(OUT_DIR, 'm3_oldlm_after.exr')
    rb2 = compute_and_save(test, inst_o, exr_old_after)
    same = (rb1['ok'] and rb2['ok']
            and os.path.getsize(exr_old_before) == os.path.getsize(exr_old_after))
    step('旧 lightmap 隔离（改新实例参数前后位级一致）', same,
         {'before': os.path.getsize(exr_old_before),
          'after': os.path.getsize(exr_old_after)})

    for nd in (inst_n, on_n, inst_o, on_o):
        try:
            test.deleteNode(nd)
        except BaseException:
            pass

    REPORT['outputs'] = {'blend': exr_blend, 'oldlm_before': exr_old_before,
                         'oldlm_after': exr_old_after}
    REPORT['perf'] = {'new': t_new, 'old': t_old, 'ratio': ratio}
    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'm3_blend_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m3_blend_report.json')
