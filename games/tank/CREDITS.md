# 坦克大战 · 来源说明

## 原创内容

- 规则、6 份关卡布局、敌军 AI、终端界面与字形均为本项目原创代码，随本游戏的 [LICENSE](LICENSE)（MIT）发布。
- 战场字形（错缝砖墙、铆钉钢墙、`▟▙` 坦克剪影等）为本项目自绘，未使用任何原版像素素材。

## 参考与致敬

| 上游 | 复用范围 | 说明 |
| --- | --- | --- |
| Namco《Battle City》（1985，FC） | 仅玩法类型 | 守卫基地、可破坏砖墙与钢墙的玩法概念；未复制其地图、美术、音效或代码 |
| [feichao93/battle-city](https://github.com/feichao93/battle-city/tree/86c41c8c3c49cd27255bcf63167091d1061801fa)（MIT，2026-10-08 查阅） | 无代码或素材复用 | 参考 `src/stages/`、`src/engine/map/parseStage.ts`、`src/engine/GameSession.ts` 的关卡配置与对局分离；未导入其经典地图或美术、音效 |
| [tirinox/pybattlecity](https://github.com/tirinox/pybattlecity/tree/69ea5c442e891adc838cdb6e8c6b2edcbb40c841)（MIT，2026-10-08 查阅） | 无代码或素材复用 | 研究 `data/level1.txt`、`data/level2.txt` 与 `field.py` 的文字地图加载方式 |
| [gunnerson/battlecity](https://github.com/gunnerson/battlecity/tree/3c746b7925a6291a659db62ef44b21b8a07dd06e)（MIT，2026-10-08 查阅） | 无代码或素材复用 | 研究 `src/Stages.hpp` 的多关卡地形组织；未导入地图与素材 |

新增关卡或素材时，请按 [社区贡献规范](../../docs/community-contribution.md) 第 3 节补充来源记录。
