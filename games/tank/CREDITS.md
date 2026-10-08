# 坦克大战 · 来源说明

## 经典关卡导入

来源：[feichao93/battle-city](https://github.com/feichao93/battle-city/tree/86c41c8c3c49cd27255bcf63167091d1061801fa)，固定提交 `86c41c8c3c49cd27255bcf63167091d1061801fa`，2026-10-08 导入。

- 完整复制 `src/stages/stage-1.json`～`stage-35.json` 到 `tank_battle/stages/`，保留原文件内容、关卡顺序、地形与敌军出场队列。
- 参照 `src/engine/map/parseStage.ts` 在 Python 中适配砖墙十六进制象限解析；参照 `constants.ts` 的基地、出生点、敌军分数、装甲耐久、增援间隔、道具敌军编号与额外生命阈值。
- 参考 `GameSession.ts`、`PauseMenu.tsx` 与标题／选关／结算界面的流程，在 curses 中重新实现独立单人菜单与战役。
- 保留上游完整 MIT 许可证及版权声明，见 [LICENSE.battle-city](LICENSE.battle-city)，Copyright (c) 2026 feichao93。

## 本项目实现

Python 战斗规则、寻路、离散碰撞、道具、战役快照、curses 菜单及终端字形在本项目中实现，依本游戏 [LICENSE](LICENSE)（MIT）发布。未导入上游图片、音频、SVG 坦克或 React/PixiJS 渲染代码。

Classic Battle City（Namco，1985）是玩法与关卡的原作。本项目以开源复刻项目的关卡数据为来源，属于终端单人适配，非官方作品。原始游戏的名称与权利归相应权利人所有。

此前研究过 [tirinox/pybattlecity](https://github.com/tirinox/pybattlecity/tree/69ea5c442e891adc838cdb6e8c6b2edcbb40c841) 和 [gunnerson/battlecity](https://github.com/gunnerson/battlecity/tree/3c746b7925a6291a659db62ef44b21b8a07dd06e) 的文字地图组织，本次没有复制其代码或素材。

后续导入内容按 [社区贡献规范](../../docs/community-contribution.md) 补充来源记录。
