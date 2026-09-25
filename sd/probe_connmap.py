# -*- coding: utf-8 -*-
r"""读取 PP 每个 input 引脚的连接源（决定性引脚-源映射）。
遍历 test 图全部 PP，枚举 Input 属性连接：getPropertyConnections。
输出：sd/validation/conn_map.json
"""
import json
import os
import sys

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

REPORT_PATH = os.path.join(SD_DIR, 'validation', 'conn_map.json')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from aniso_pp import api as SDAPI

    res = {'pps': [], 'fail': None}
    try:
        graph = SDAPI.get_current_graph()
        nodes = graph.getNodes()
        for i in range(nodes.getSize()):
            node = nodes.getItem(i)
            try:
                if node.getDefinition().getId() != SDAPI.PP_NODE_ID:
                    continue
            except BaseException:
                continue
            pp_info = {'connections': []}
            props = node.getProperties(SDPropertyCategory.Input)
            for j in range(props.getSize()):
                p = props.getItem(j)
                pid = p.getId()
                if not pid.startswith('input'):
                    continue
                conns = node.getPropertyConnections(p)
                src_desc = None
                if conns.getSize() > 0:
                    c = conns.getItem(0)
                    src_node = c.getInputPropertyNode()  # 源节点（counter-intuitive 但官方语义）
                    try:
                        src_def = src_node.getDefinition().getId()
                    except BaseException:
                        src_def = '?'
                    src_res = ''
                    try:
                        rr = src_node.getReferencedResource()
                        if rr is not None:
                            src_res = rr.getUrl()
                    except BaseException:
                        pass
                    src_desc = {'def': src_def, 'res': src_res}
                pp_info['connections'].append(
                    {'pin': pid, 'connected': conns.getSize() > 0,
                     'source': src_desc})
            res['pps'].append(pp_info)
        res['ok'] = True
    except BaseException:
        import traceback as tb
        res['fail'] = tb.format_exc()

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('[DONE]')


main()
