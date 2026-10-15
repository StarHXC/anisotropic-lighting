# -*- coding: utf-8 -*-
import json, os, sys, traceback
SD_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SD_DIR, chr(118)+chr(97)+chr(108)+chr(105)+chr(100)+chr(97)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(101)+chr(97)+chr(115)+chr(121)+chr(108)+chr(105)+chr(103)+chr(104)+chr(116), chr(111)+chr(117)+chr(116))
os.makedirs(OUT, exist_ok=True)
rep = {chr(112)+chr(114)+chr(111)+chr(98)+chr(101): chr(100)+chr(105)+chr(97)+chr(103)}
try:
    import sd
    from aniso_pp import api as SDAPI
    g = SDAPI.get_current_graph()
    rep[chr(103)+chr(114)+chr(97)+chr(112)+chr(104)] = str(g)
    if g is not None:
        rep[chr(116)+chr(105)+chr(116)+chr(108)+chr(101)] = SDAPI.get_graph_title(g)
    rep[chr(111)+chr(107)] = True
except BaseException as e:
    rep[chr(102)+chr(97)+chr(105)+chr(108)] = repr(e)
with open(os.path.join(OUT, chr(100)+chr(105)+chr(97)+chr(103)+chr(46)+chr(106)+chr(115)+chr(111)+chr(110)), chr(119), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as f:
    json.dump(rep, f)
print(chr(68)+chr(79)+chr(78)+chr(69))
