"""validation/diag_font.py — 最小化验证中文字体加载 API。"""
import sys

import imgui_bundle.imgui as imgui

imgui.create_context()
io = imgui.get_io()
font = io.fonts.add_font_from_file_ttf(r"C:\Windows\Fonts\msyh.ttc", 16.0)
print("font loaded:", font is not None)
sys.exit(0)
