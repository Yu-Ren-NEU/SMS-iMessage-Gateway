# 可替换摆件

- `robot-original.stl` / `.step`：原 V0.32 机器人，4.0 mm 方插柱，实物偏松。
- `astronaut-plugin.stl`、`cat-plugin.stl`、`tv-plugin.stl`：新版三个形象 V2，4.2 mm 方插柱、插入 1.65 mm、末端 0.25 mm 导入倒角，适配现有 4.4 mm 方盲孔。
- `review.png`：三个插件单体和装在现有外壳上的预览。
- `generate_astronaut.py`、`generate_cat_tv.py`：CadQuery 源码。STL 单位为 mm，主体高约 24 mm，底座 21×18 mm。

交给打印店的是 STL。源代码、预览不需打印；无需重打盒子。最终网格经零面积面清理和封闭性检查。实物松紧仍待验证，不要硬压插柱。用不同机器打印时可先打印一个插件测试；不要整体缩放来调整插头，否则摆件也会改变。
