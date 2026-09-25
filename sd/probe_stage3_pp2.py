# -*- coding: utf-8 -*-
r"""桥执行版 = stage3_pp2.py 的薄转发（单一事实源，避免双拷贝漂移）。"""
import os

_SD_DIR = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_SD_DIR, 'stage3_pp2.py')
exec(compile(open(_src, encoding='utf-8').read(), _src, 'exec'))
