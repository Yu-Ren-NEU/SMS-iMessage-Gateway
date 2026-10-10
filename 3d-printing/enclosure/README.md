# V0.32 — square, four-direction mascot plug
The interchangeable robot is a separate fourth printable part. Its base has one 4.0 × 4.0 mm square peg; the white top cover has one 4.4 × 4.4 mm square blind socket. The nominal 0.4 mm overall width difference on each axis matches the existing 2.5 mm pin / 2.9 mm socket difference inside the case. The square allows four orientations, changing direction in 90-degree steps.
The peg extends 1.65 mm below the mascot base, with 0.25 mm clearance at the bottom of the blind socket. The blind socket leaves 0.6 mm of intact roof. Internal pillars, case, carrier and all other geometry are unchanged. Test PETG fit gently before fully seating.

## 打印文件范围

打印 `base.stl`、`lid-carrier.stl`、`top-cover.stl` 三件，单位 mm。原机器人已经移到 `../plugins/`，不属于盒子本体。STEP 用于修改，PNG 用于预览，JSON 是参数记录；无需打印这些辅助文件。

使用 `generate_enclosure.py` 重新生成需要 CadQuery 和 macOS Apple Chancery 字体；不会覆盖本说明。
