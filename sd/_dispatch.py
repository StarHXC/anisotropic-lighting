# -*- coding: utf-8 -*-
"""协议 v2 调度器（对齐已装 sd_bridge v2.2 / bridge_core.py）。

用法：python _dispatch.py <probe名> [timeout秒]
退出码：0=ok 1=探针失败 2=超时。
"""
import json
import os
import sys
import time
import uuid

probe = sys.argv[1]
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

TASK_PATH = r'E:\AI_Project\Anisotropic Lighting\sd\validation\_bridge_task.json'
RESULT_PATH = r'E:\AI_Project\Anisotropic Lighting\sd\validation\_bridge_result.json'

request_id = uuid.uuid4().hex
if os.path.exists(RESULT_PATH):
    os.remove(RESULT_PATH)
with open(TASK_PATH, 'w', encoding='utf-8') as f:
    json.dump({'protocol': 2, 'probe': probe, 'request_id': request_id,
               'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, f)
print('[DISPATCH]', probe, request_id)

t0 = time.time()
while time.time() - t0 < timeout:
    if os.path.exists(RESULT_PATH):
        r = json.load(open(RESULT_PATH, encoding='utf-8'))
        if r.get('request_id') != request_id or r.get('probe') != probe:
            time.sleep(1.0)
            continue
        print('[RESULT]', json.dumps({k: r.get(k) for k in ('probe', 'ok')},
                                     ensure_ascii=False))
        if r.get('note'):
            print('[NOTE]', r['note'])
        if r.get('error'):
            print(r['error'][-1500:])
        sys.exit(0 if r.get('ok') is True else 1)
    time.sleep(1.0)
print('[TIMEOUT]')
sys.exit(2)
