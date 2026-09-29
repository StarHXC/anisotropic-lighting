# -*- coding: utf-8 -*-
r"""M3 — aniso_easylight 真实资产 + 旧节点 parity 探针。

1. easylight 默认参数 2048² 渲染（缓存击破后）→ m3_default.exr
2. 旧 aniso_lightmap 按等价性命题设置 35 参数 → m3_old_equiv.exr
   （五色白/ambient 黑、intensity 旧默认、spec 旧默认、diffuse_mode=0、
    view normal_proxy、exposure_ev=0、validity_fill=0）
3. 性能冒烟：新旧热更新中位数各 3 次
输出: validation_easylight/out/m3/
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
           or k == 'aniso_easylight_tools' or k.startswith('aniso_easylight_tools.')
           or k == 'stages']:
    del sys.modules[_k]

OUT_DIR = os.path.join(SD_DIR, 'validation_easylight', 'out', 'm3')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'easylight_m3', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'M3 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2, int2
    from sd.api.sdvaluefloat import SDValueFloat
    from sd.api.sdvalueint import SDValueInt
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    test = SDAPI.get_current_graph()

    # ---- 资源解析
    easy_res = lm_res = None
    for i in range(pkg_mgr.getPackages().getSize()):
        p_ = pkg_mgr.getPackages().getItem(i)
        try:
            if easy_res is None:
                r = p_.findResourceFromUrl('pkg:///aniso_easylight')
                if r is not None:
                    easy_res = r
            if lm_res is None:
                r = p_.findResourceFromUrl('pkg:///aniso_lightmap')
                if r is not None:
                    lm_res = r
        except BaseException:
            continue
    step('解析资源', easy_res is not None and lm_res is not None,
         {'easylight': easy_res is not None, 'lightmap': lm_res is not None})

    # 清扫测试图旧实例
    nodes_all = test.getNodes()
    for i in range(nodes_all.getSize()):
        nd = nodes_all.getItem(i)
        try:
            rr = nd.getReferencedResource()
            url = str(rr.getUrl()) if rr is not None else ''
            if 'aniso_easylight' in url or 'aniso_lightmap' in url:
                test.deleteNode(nd)
        except BaseException:
            continue

    # ---- 1. easylight 默认渲染
    inst = test.newInstanceNode(easy_res)
    inst.setPosition(float2(8000.0, 2000.0))
    outs = inst.getProperties(SDPropertyCategory.Output)
    pin = str(outs.getItem(0).getId())
    on = test.newNode('sbs::compositing::output')
    on.setPosition(float2(8600.0, 2000.0))
    inst.newPropertyConnectionFromId(pin, on, 'inputNodeOutput')

    prop = inst.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
    inst.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
    inst.setPropertyValue(prop, SDValueInt2.sNew(int2(10, 10)))
    test.compute()
    inst.setPropertyValue(prop, SDValueInt2.sNew(int2(11, 11)))
    test.compute()
    rb = compute_and_save(test, inst, os.path.join(OUT_DIR, 'm3_default.exr'))
    step('easylight 默认渲染', rb['ok'], {'size': rb['size']})

    # ---- 2. 旧 lightmap 等价参数渲染
    inst_o = test.newInstanceNode(lm_res)
    inst_o.setPosition(float2(8000.0, 2600.0))
    outs_o = inst_o.getProperties(SDPropertyCategory.Output)
    pin_o = str(outs_o.getItem(0).getId())
    on_o = test.newNode('sbs::compositing::output')
    on_o.setPosition(float2(8600.0, 2600.0))
    inst_o.newPropertyConnectionFromId(pin_o, on_o, 'inputNodeOutput')

    def set_o(pid, v):
        pr = inst_o.getPropertyFromId(pid, SDPropertyCategory.Input)
        if pid in ('p_two_sided', 'p_aniso_axis', 'p_spec_mode',
                   'p_diffuse_mode', 'p_view_mode'):
            inst_o.setPropertyValue(pr, SDValueInt.sNew(int(round(v))))
        else:
            inst_o.setPropertyValue(pr, SDValueFloat.sNew(float(v)))

    # 等价性命题参数（int 类用 SDValueInt，颜色 float3 无需动——默认即白；
    # ambient_color 需要置黑，但它没有注解 min/max 限制，直接设 float3 值）
    from sd.api.sdvaluefloat3 import SDValueFloat3
    from sd.api.sdbasetypes import float3
    pr_amb = inst_o.getPropertyFromId('p_ambient_color', SDPropertyCategory.Input)
    inst_o.setPropertyValue(pr_amb, SDValueFloat3.sNew(float3(0.0, 0.0, 0.0)))
    set_o('p_diffuse_mode', 0)
    set_o('p_exposure_ev', 0.0)
    set_o('p_validity_fill', 0.0)
    set_o('p_exposure_ev', 0.0)
    # spec/diffuse 其余分段、intensity、front_k、view 组均为旧默认（parity 命题）

    prop_o = inst_o.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
    inst_o.setPropertyInheritanceMethod(prop_o, SDPropertyInheritanceMethod.Absolute)
    inst_o.setPropertyValue(prop_o, SDValueInt2.sNew(int2(10, 10)))
    test.compute()
    inst_o.setPropertyValue(prop_o, SDValueInt2.sNew(int2(11, 11)))
    test.compute()
    rb_o = compute_and_save(test, inst_o, os.path.join(OUT_DIR, 'm3_old_equiv.exr'))
    step('旧 lightmap 等价参数渲染', rb_o['ok'], {'size': rb_o['size']})

    # ---- 3. 性能冒烟（热更新中位数各 3 次）
    def time_it(node, runs=3):
        pr = node.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
        times = []
        for _ in range(runs):
            node.setPropertyValue(pr, SDValueInt2.sNew(int2(10, 10)))
            test.compute()
            node.setPropertyValue(pr, SDValueInt2.sNew(int2(11, 11)))
            t0 = time.perf_counter()
            test.compute()
            times.append(time.perf_counter() - t0)
        return {'median_s': statistics.median(times),
                'runs': [round(t, 4) for t in times]}

    t_new = time_it(inst)
    t_old = time_it(inst_o)
    step('性能冒烟（记录，无门禁）', True,
         {'easylight': t_new, 'lightmap(PP1+PP2)': t_old})
    REPORT['perf'] = {'easylight': t_new, 'lightmap': t_old}

    for nd in (inst, inst_o, on, on_o):
        try:
            test.deleteNode(nd)
        except BaseException:
            pass

    REPORT['ok'] = True


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(OUT_DIR, 'm3_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m3_report.json')
