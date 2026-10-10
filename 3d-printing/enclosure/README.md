# V0.32 — square, four-direction mascot plug
The interchangeable robot is a separate fourth printable part. Its base has one 4.0 × 4.0 mm square peg; the white top cover has one 4.4 × 4.4 mm square blind socket. The nominal 0.4 mm overall width difference on each axis matches the existing 2.5 mm pin / 2.9 mm socket difference inside the case. The square allows four orientations, changing direction in 90-degree steps.
The peg extends 1.65 mm below the mascot base, with 0.25 mm clearance at the bottom of the blind socket. The blind socket leaves 0.6 mm of intact roof. Internal pillars, case, carrier and all other geometry are unchanged. Test PETG fit gently before fully seating.

## 打印文件范围

打印 `base.stl`、`lid-carrier.stl`、`top-cover.stl` 三件，单位 mm。原机器人已经移到 `../plugins/`，不属于盒子本体。STEP 用于修改，PNG 用于预览，JSON 是参数记录；无需打印这些辅助文件。

使用 `generate_enclosure.py` 重新生成需要 CadQuery 和 macOS Apple Chancery 字体；不会覆盖本说明。

## 实物验收与打印记录

当前没有最终版本的切片工程、实测克重、耗材品牌或完整打印参数；不要将 CAD 配合尺寸当作打印后保证值。STL 按 100% 比例、mm 单位导入；支撑、层高和摆放由打印店按机器检查。外壳选黑色 PETG（base / lid-carrier）和石灰白 PETG（top-cover），插件颜色可另选。

| 验收项 | 应记录的结果 |
|---|---|
| 打印条件 | 机器、喷嘴、耗材、层高、壁圈、填充、方向、支撑及切片总重量（包含支撑） |
| 配合 | 插柱/孔实际尺寸；徒手轻插能否就位，是否晃动、开裂，是否可拔出 |
| 外壳 | 四柱支撑及盖子闭合、USB 插头/卡槽操作、天线锁紧；不得挤压 PCB 或针脚 |
| 摆件 | 四个方向试插、重心稳定、眼口清晰；4.2 mm 插头尚待实测，不要强压 |
| 使用后 | 连续运行的外壳温度、变形、插拔后的松紧变化 |

先试一个插件和现有顶盖配合，再决定是否批量打印。调整松紧时仅改插头/孔参数，不要整体缩放，也不要改内部安装柱。已有实物反馈：原 4.0 mm 方插柱偏松；新 V2 增至 4.2 mm，顶盖孔保持 4.4 mm，名义单侧间隙 0.1 mm。

### 最新用户实物反馈

最终外壳装配确认通过，日常长期运行稳定；断电重连后模块自动上电，短信功能恢复。新 4.2 mm 插头目前插不进去，计划重新打印复核；原因尚未确认。专门的温度测量和故障注入测试尚未记录。
