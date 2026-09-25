# -*- coding: utf-8 -*-
"""SD 计算结果读回（Stage 0 共享模块）。

链路（官方示例 sample_sbs_graph_icon.py:61-69 实证）：
    graph.compute()                      # 阻塞直到输出可用
    node.getPropertyValue(output_prop)   # SDTypeTexture → SDValueTexture
    value.get()                          # → SDTexture
    texture.save(path, '')               # outputColorSpace='' = 无色彩变换（§8.1）

用途：0B/0C/0D 的数值验证从「用户手动导出」变为「API 自动落盘」。
"""
from __future__ import annotations


def compute_and_save(graph, node, out_path: str, *, output_prop_id: str | None = None):
    """计算 graph 并把 node 的输出纹理保存到 out_path。

    - graph.compute() 阻塞（sdsbscompgraph.py:61）
    - output_prop_id 为 None 时取 node 的第一个 Output 属性
      （PP 的输出 = unique_filter_output；compositing::output 节点亦同）
    - save 的 outputColorSpace 传空串 → 不做色彩变换（sdtexture.py:97-104）
    返回 {'ok': bool, 'size': (w,h) | None, 'error': str | None}。
    """
    from sd.api.sdproperty import SDPropertyCategory

    try:
        graph.compute()
        if output_prop_id is None:
            props = node.getProperties(SDPropertyCategory.Output)
            if props.getSize() == 0:
                return {'ok': False, 'size': None, 'error': 'node 无 Output 属性'}
            prop = props.getItem(0)
        else:
            prop = node.getPropertyFromId(output_prop_id, SDPropertyCategory.Output)
            if prop is None:
                return {'ok': False, 'size': None,
                        'error': f'Output 属性不存在: {output_prop_id}'}
        val = node.getPropertyValue(prop)
        if val is None:
            return {'ok': False, 'size': None, 'error': 'getPropertyValue 返回 None'}
        tex = val.get()
        if tex is None:
            return {'ok': False, 'size': None, 'error': 'SDValueTexture.get() 返回 None'}
        size = tex.getSize()
        tex.save(out_path, '')  # 空串 = 无色彩变换
        return {'ok': True, 'size': (size.x, size.y), 'error': None}
    except BaseException as e:
        import traceback
        return {'ok': False, 'size': None,
                'error': f'{e!r}\n{traceback.format_exc()}'}
