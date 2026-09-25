"""临时诊断脚本：检查 Tuv 各 texel 的 GPU/CPU 值与行列方向。

已由 validation/suite.py（G1 全通过）取代；保留作快速目视诊断，不复数运行。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import validation.suite as vs
from gl.context import RenderContext

SIZE = 64
rc = RenderContext.standalone(SIZE, SIZE)
pos_u16, mask = vs.make_plane_position(SIZE)
normal_enc = vs.make_plane_normal(SIZE, (0.0, 0.0, 1.0))
ref = vs.cpu_reference(pos_u16.astype(np.float64) / 65535.0,
                       mask.astype(np.float64), normal_enc)
tuv = vs.run_gpu_case(rc, pos_u16, mask, normal_enc, debug_mode=3)
got = tuv[..., :3] * 2.0 - 1.0

print("CPU ref Tuv [32,32]:", ref["tuv"][32, 32].round(5))
print("CPU ref Tuv [63,63]:", ref["tuv"][63, 63].round(5))
print("CPU ref Tuv [0,0]:", ref["tuv"][0, 0].round(5))
print("CPU ref dPdqx[32,32]:", ref["dpdqx"][32, 32].round(6))
print("CPU ref dPdqy[32,32]:", ref["dpdqy"][32, 32].round(6))
print("CPU ref dqx_valid[32,32]:", ref["dqx_valid"][32, 32],
      "dqy_valid:", ref["dqy_valid"][32, 32])
print("CPU ref dPdqx[63,63]:", ref["dpdqx"][63, 63].round(6))
print("CPU ref dPdqy[63,63]:", ref["dpdqy"][63, 63].round(6))
print("GPU got Tuv [32,32]:", got[32, 32].round(5))
print("GPU got Tuv [63,63]:", got[63, 63].round(5))
rc.release()
