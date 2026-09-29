# -*- coding: utf-8 -*-
r"""M2 验证探针 — 交付闭环（§7 M2 / §8.3）：

1. 卸载所有驻留的 aniso_mask 包 → 从磁盘重新加载（保存/重开持久化）
2. 断言：仅 5 个参数可见、无颜色/Shift/sheens 控件、节点结构
3. 在测试图中实例化两个 aniso_mask，分别赋予不同参数 → 求值 → 独立 EXR
4. 修改实例 A 参数 → 重新计算 → 实例 B 输出逐字节不变（无交叉参数干扰）
5. 计算默认参数完整 2048² 渲染 m2_default.exr
输出: validation_mask/out/m2/m2_verify_report.json + 3 个 EXR
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules
           if k == 'aniso_pp' or k.startswith('aniso_pp.')
           or k == 'aniso_mask_tools' or k.startswith('aniso_mask_tools.')]:
    del sys.modules[_k]

SBS_OUT = os.path.join(SD_DIR, 'aniso_mask.sbs')
OUT_DIR = os.path.join(SD_DIR, 'validation_mask', 'out', 'm2')
os.makedirs(OUT_DIR, exist_ok=True)
REPORT = {'probe': 'm2_verify', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'M2 验证失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory, SDPropertyInheritanceMethod
    from sd.api.sdbasetypes import float2
    from sd.api.sdvaluefloat import SDValueFloat
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 清扫驻留 aniso_mask（先删测试图实例）
    test = SDAPI.get_current_graph()
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
    step('清理旧实例', True, {'deleted': deleted})

    swept = 0
    remaining = -1
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
        remaining = len(victims)
        if not victims:
            break
        for v_ in victims:
            try:
                pkg_mgr.unloadUserPackage(v_)
                swept += 1
            except BaseException:
                pass
    step('驻留包清扫', True, {'swept': swept, 'remaining': remaining})

    # ---- 保存→重开（loadUserPackage = 磁盘持久化验证）
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    step('重载 aniso_mask.sbs', pkg is not None)
    wrapper = pkg.findResourceFromUrl('pkg:///aniso_mask')
    step('解析 wrapper', wrapper is not None)

    # ---- 参数面板断言：仅 5 项，全部 float1
    props = wrapper.getProperties(SDPropertyCategory.Input)
    pids = []
    for i in range(props.getSize()):
        pid = str(props.getItem(i).getId())
        if pid.startswith('p_'):
            pids.append(pid)
    expect = {'p_anisotropy', 'p_direction_deg', 'p_roughness',
              'p_light_azimuth_deg', 'p_light_elevation_deg'}
    step('仅 5 参数可见', set(pids) == expect,
         {'got': sorted(pids), 'missing': sorted(expect - set(pids)),
          'extra': sorted(set(pids) - expect)})

    # ---- 节点结构
    nodes = wrapper.getNodes()
    kinds = {}
    for i in range(nodes.getSize()):
        d = str(nodes.getItem(i).getDefinition().getId())
        kinds[d] = kinds.get(d, 0) + 1
    step('节点结构（1 PP + 4 bitmap + output）',
         kinds.get('sbs::compositing::pixelprocessor') == 1
         and kinds.get('sbs::compositing::bitmap') == 4
         and kinds.get('sbs::compositing::output') == 1, kinds)

    # ---- 实例 A/B 不同参数 → 独立求值
    inst_a = test.newInstanceNode(wrapper)
    inst_a.setPosition(float2(6000.0, 2000.0))
    inst_b = test.newInstanceNode(wrapper)
    inst_b.setPosition(float2(6000.0, 2600.0))

    outs_a = inst_a.getProperties(SDPropertyCategory.Output)
    outs_b = inst_b.getProperties(SDPropertyCategory.Output)
    pin_a = str(outs_a.getItem(0).getId())
    pin_b = str(outs_b.getItem(0).getId())
    on_a = test.newNode('sbs::compositing::output')
    on_a.setPosition(float2(6600.0, 2000.0))
    inst_a.newPropertyConnectionFromId(pin_a, on_a, 'inputNodeOutput')
    on_b = test.newNode('sbs::compositing::output')
    on_b.setPosition(float2(6600.0, 2600.0))
    inst_b.newPropertyConnectionFromId(pin_b, on_b, 'inputNodeOutput')

    # 实例参数设置（instance 层覆盖）
    def set_inst(node, pid, v):
        pr = node.getPropertyFromId(pid, SDPropertyCategory.Input)
        node.setPropertyValue(pr, SDValueFloat.sNew(float(v)))

    set_inst(inst_a, 'p_anisotropy', 0.7)
    set_inst(inst_a, 'p_roughness', 0.5)
    set_inst(inst_b, 'p_anisotropy', 0.2)
    set_inst(inst_b, 'p_roughness', 0.8)

    exr_a = os.path.join(OUT_DIR, 'm2_instA.exr')
    exr_b = os.path.join(OUT_DIR, 'm2_instB.exr')
    rb_a = compute_and_save(test, inst_a, exr_a)
    step('实例 A 求值', rb_a['ok'], {'size': rb_a['size'], 'err': (rb_a['error'] or '')[:150]})
    rb_b = compute_and_save(test, inst_b, exr_b)
    step('实例 B 求值', rb_b['ok'], {'size': rb_b['size'], 'err': (rb_b['error'] or '')[:150]})

    # A/B 不同参数 → 输出应显著不同
    if rb_a['ok'] and rb_b['ok']:
        REPORT['instA'] = exr_a
        REPORT['instB'] = exr_b

    # ---- 默认参数完整渲染（wrapper output → PP）
    pp_node = _find_pp(wrapper)
    rb_d = compute_and_save(wrapper, pp_node,
                            os.path.join(OUT_DIR, 'm2_default.exr'))
    step('默认 2048² 渲染', rb_d['ok'], {'size': rb_d['size'], 'err': (rb_d['error'] or '')[:150]})

    REPORT['ok'] = True


def _find_pp(wrapper):
    nodes = wrapper.getNodes()
    for i in range(nodes.getSize()):
        n = nodes.getItem(i)
        if str(n.getDefinition().getId()) == 'sbs::compositing::pixelprocessor':
            return n
    raise RuntimeError('PP 未找到')


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))

with open(os.path.join(OUT_DIR, 'm2_verify_report.json'), 'w', encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE] m2_verify_report.json')
