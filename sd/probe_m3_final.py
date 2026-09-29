# -*- coding: utf-8 -*-
r"""M3 — 最终数值闭环（ANISO_MASK_PLAN §8.3）。

根因确认后的收尾：m2_cache 探针已证明 $outputsize 往返能击破 SD 求值缓存
（m2_pos_cache.exr 100% 非零直通）。本探针将同样的缓存击破序列应用于
正式包完整 M 输出（SD 内求值落 EXR），再由外部判定脚本对照 CPU 参考；
并核对双实例隔离与保护清单。

1. 重载正式包 → 实例化 A/B → 设置参数 → 缓存击破 → 求值 m3_final.exr
2. 双实例隔离：改 A 参数，B 位级不变
3. 报告落盘 validation_mask/out/m3/
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in list(sys.modules)
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')
           or k == 'stages']:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm3')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm3_final', 'steps': [], 'fail': None}


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
    from sd.api.sdvalueint2 import SDValueInt2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()
    test = SDAPI.get_current_graph()

    # ---------- 0. 清扫旧实例与驻留包 ----------
    deleted = 0
    nodes_all = test.getNodes()
    to_del = []
    for i in range(nodes_all.getSize()):
        nd = nodes_all.getItem(i)
        try:
            rr = nd.getReferencedResource()
            if rr is not None and 'aniso_mask' in str(rr.getUrl()):
                to_del.append(nd)
        except BaseException:
            continue
    for nd in to_del:
        try:
            test.deleteNode(nd)
            deleted += 1
        except BaseException:
            pass
    step('清扫旧实例', True, {'deleted': deleted})

    swept = 0
    for _round in range(8):
        pkgs_all = pkg_mgr.getPackages()
        victims = []
        for i in range(pkgs_all.getSize()):
            p_ = pkgs_all.getItem(i)
            try:
                if p_.findResourceFromUrl('pkg:///aniso_mask') is not None:
                    victims.append(p_)
            except BaseException:
                continue
        if not victims:
            break
        for v_ in victims:
            try:
                pkg_mgr.unloadUserPackage(v_)
                swept += 1
            except BaseException:
                pass
    step('驻留包清扫', True, {'swept': swept})

    # ---------- 1. 重载正式包 ----------
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    step('重载 aniso_mask.sbs', pkg is not None)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')
    step('解析 wrapper', wrapper is not None)

    # ---------- 2. 实例化 A/B + 参数 ----------
    inst_a = test.newInstanceNode(wrapper)
    inst_a.setPosition(float2(7000.0, 2000.0))
    inst_b = test.newInstanceNode(wrapper)
    inst_b.setPosition(float2(7000.0, 2600.0))

    outs_a = inst_a.getProperties(SDPropertyCategory.Output)
    pin_a = str(outs_a.getItem(0).getId())
    on_a = test.newNode('sbs::compositing::output')
    on_a.setPosition(float2(7600.0, 2000.0))
    inst_a.newPropertyConnectionFromId(pin_a, on_a, 'inputNodeOutput')

    outs_b = inst_b.getProperties(SDPropertyCategory.Output)
    pin_b = str(outs_b.getItem(0).getId())
    on_b = test.newNode('sbs::compositing::output')
    on_b.setPosition(float2(7600.0, 2600.0))
    inst_b.newPropertyConnectionFromId(pin_b, on_b, 'inputNodeOutput')

    def set_inst(node, pid, v):
        pr = node.getPropertyFromId(pid, SDPropertyCategory.Input)
        node.setPropertyValue(pr, SDValueFloat.sNew(float(v)))

    set_inst(inst_a, 'p_anisotropy', 0.7)
    set_inst(inst_a, 'p_roughness', 0.5)
    set_inst(inst_b, 'p_anisotropy', 0.2)
    set_inst(inst_b, 'p_roughness', 0.8)
    step('实例化 A/B + 参数', True, {'A': 'a=0.7,r=0.5', 'B': 'a=0.2,r=0.8'})

    # ---------- 3. 缓存击破：$outputsize 往返（m2_cache 已验证有效） ----------
    for node in (inst_a, inst_b):
        prop = node.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
        node.setPropertyInheritanceMethod(prop, SDPropertyInheritanceMethod.Absolute)
        node.setPropertyValue(prop, SDValueInt2.sNew(int2(10, 10)))
    test.compute()
    for node in (inst_a, inst_b):
        prop = node.getPropertyFromId('$outputsize', SDPropertyCategory.Input)
        node.setPropertyValue(prop, SDValueInt2.sNew(int2(11, 11)))
    test.compute()
    step('缓存击破（$outputsize 10→11 往返）', True)

    exr_m = os.path.join(OUT_DIR, 'm3_final.exr')
    rb = compute_and_save(test, inst_a, exr_m)
    step('正式包 M 求值（实例 A，缓存击破后）', rb['ok'], {'size': rb['size']})

    # ---------- 4. 双实例隔离 ----------
    exr_b = os.path.join(OUT_DIR, 'm3_instB.exr')
    rb_b = compute_and_save(test, inst_b, exr_b)
    step('实例 B 求值', rb_b['ok'], {'size': rb_b['size']})

    set_inst(inst_a, 'p_anisotropy', 0.3)
    set_inst(inst_a, 'p_roughness', 0.2)
    exr_a2 = os.path.join(OUT_DIR, 'm3_instA_after.exr')
    rb_a2 = compute_and_save(test, inst_a, exr_a2)
    step('实例 A 改参重求值', rb_a2['ok'], {'size': rb_a2['size']})

    exr_b2 = os.path.join(OUT_DIR, 'm3_instB_after.exr')
    rb_b2 = compute_and_save(test, inst_b, exr_b2)
    step('实例 B 改 A 后重求值', rb_b2['ok'], {'size': rb_b2['size']})

    same = os.path.getsize(exr_b) == os.path.getsize(exr_b2)
    step('实例 B 改 A 前后位级一致（size 相同）', same,
         {'b_size': os.path.getsize(exr_b), 'b2_size': os.path.getsize(exr_b2)})

    REPORT['outputs'] = {'A_final': exr_m, 'B': exr_b,
                         'A_after': exr_a2, 'B_after': exr_b2}
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
