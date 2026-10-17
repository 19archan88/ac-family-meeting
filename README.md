# ac-family-meeting · 每周家庭会议

将家庭会议转写或文字记录，整理为可追溯、可回顾的纪要、分析和成长档案。用于支持平等协商、行动回顾与家庭共读，不是通用商务会议工具，也不是独立运行的录音应用。

## 功能

- 每场会议生成一份一体化周报：事实性纪要＋孩子与照顾者双镜头分析＋行动建议＋内容审计。
- 根据已提供的历史材料生成月度、学期和年度报告，注明缺失与覆盖范围。
- 首次提醒配置家庭成员、孩子生日或年龄基准、入学及年级规则、会议计划和校历。
- 按实际会议日期自动推算年龄、入学时长、年级；支持多孩子、自定义学制、升级日期和学籍变更后的历史回算。
- 核验会议届数、重复来源、历史补录和修订；按稳定 ID 更新状态，避免重复计数。
- 默认先保存并打开完整 Markdown，再自动生成离线 HTML、检查归档并打开阅读版，最终交付全文及文件链接。环境无法打开文件时提供链接并如实说明。
- HTML 提供 PDF 和单张长图 PNG 导出按钮；默认不预先生成独立 PDF／PNG。

## 安装与首次使用

```sh
git clone https://github.com/19archan88/ac-family-meeting.git
```

将整个 `ac-family-meeting` 文件夹放入所用 AI Agent 的技能目录，或按其支持的方式导入。保持 SKILL.md、agents、references、scripts、assets 的相对位置不变。业务规范已包含在随包引用文档中，不需要原作者的 Word 文件。需要支持读取技能与本地文件的 Agent；脚本使用 Python 3 标准库，阅读及导出 HTML 需要现代浏览器。

首次可这样调用：

> 请使用 $ac-family-meeting 整理这份家庭会议记录。先协助我设置家庭成员、孩子年龄年级规则和校历。会议实际日期是……，实际届数是……，私有档案位置是……，以下是匿名化记录：……

家庭资料写入仓库外的私有 `FAMILY-profile.json`，详见 [家庭设置指南](references/family-setup.md) 与 [空配置模板](assets/family-profile-template.json)。不要求真实姓名。暂不愿提供的资料留空；无法精确推算时明确标注，不伪造生日或学籍。

“先审阅”“只要文字”“只要文件”“不归档”等明确要求优先。一次会议始终只算一场，不因生成多个格式增加计数。

## 工具

命令在技能目录执行，路径替换为实际私有档案位置：

```sh
python scripts/meeting_context.py 2030-05-17 --profile /private/FAMILY-profile.json --child-id child-1
python scripts/meeting_context.py 2030-05-17 --state /private/STATE-latest.json --number 3 --source /private/transcript.md
python scripts/profile_store.py status --archive /private/family-meetings --child-id child-1
```

日期工具是只读辅助，不会确认异常、证明历史完整或生成报告。多孩子须逐个指定 `--child-id`；报告合并各人的上下文。正式交付与状态增量使用 [start → ready → finish 流程](references/delivery-workflow.md)，不能直接拿示例状态覆盖旧档案。

正式交付必须提供 `--family-archive` 并通过初始化检查；用户明确选择临时模式才使用 `--no-archive --onboarding-acknowledged`。底层 HTML 生成器仅用于排版维护，不证明初始化完成。新增资料通过 profile_store.py update 合并保存，成功回读后才报告已保存；详见家庭初始化说明。

完整虚构成品：[Markdown](examples/FM-2030-006-2030-05-19.md)、[离线 HTML](examples/FM-2030-006-2030-05-19.html)。示例不创建真实家庭状态。JavaScript 不可用时保留完整文字原稿。

```sh
python -m unittest discover -s scripts -p "test_*.py"
node scripts/test_png_encoder.cjs
npm install
npm run test:presentation
```

后两条仅供维护者运行 DOM 集成测试，需要 Node.js 18 或更新版本；开发依赖不会进入离线 HTML，也不是使用技能的前置条件。可用 `PYTHON` 环境变量指定 Python 可执行文件。DOM 测试核对实际生成页面的结构和内容，不能替代真实浏览器的布局、打印与 PNG 导出检查。

呈现层以随包原有设计为基础，保留必要修复和纯文本故障回退；输入约定与各周期示例的适用范围见 [HTML 规范](references/html-delivery.md#markdown-与渲染器的约定)。提示词版本保持 `v2.0`，独立视觉版本以构建器中的 `renderVersion` 为准。

## 文件导航

| 文件／目录 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 技能入口、业务范围与执行流程 |
| [references/family-setup.md](references/family-setup.md) | 家庭初始化、自动推算和自定义校历 |
| [references/protocol.md](references/protocol.md) | 编号、触发、历史、隐私及状态规则 |
| [references/delivery-workflow.md](references/delivery-workflow.md) | 交付顺序和状态增量格式 |
| [references/](references/) | 周／月／学期／年度规范与 HTML 要求 |
| [scripts/](scripts/) | 日期校验、家庭推算、HTML、归档与测试 |
| [assets/](assets/) | 空配置及离线阅读模板 |

## 隐私与适用边界

- 家庭配置、录音、逐字稿、报告、状态与测试回执保存在仓库外；不要提交真实家庭材料。
- “这段不录”及明确要求删除的片段不进入衍生报告、状态或摘要。家长私读分析与家庭共读内容分开处理；匿名化不等于授权公开分享。
- 模板示例和测试日期均为结构演示，不是使用者的家庭事实。
- 实际校历决定学期范围；没有覆盖的区间标注未知，不自动视为暑假。
- 与 `ac-bedtime-news` 相互独立，不共享状态、会议次数、报告触发规则或行动额度。
- 自动转写、云归档及后台提醒需要另行接入并授权；本技能不自带这些能力。
- 心理学与教育视角用于观察和讨论，不作诊断，不承诺特定成长结果。

## 开源许可与版权

Copyright (c) 2026 阿昌 (19archan88)。公众号：阿昌正传。

除另有说明的第三方资源外，本项目的技能指令、文档、脚本和模板采用 [MIT License](LICENSE)。允许修改、再分发、商用和闭源衍生版本；分发副本或实质性部分时须保留版权与许可声明。按现状提供，保证及责任限制以 LICENSE 原文为准。第三方资源详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，各自原始许可随包保留。

报告默认署名用于标识模板来源，不代表模板作者撰写或审核了用户报告。用户可修改或移除可见公众号署名；这不免除再分发代码时保留许可声明的义务。离线 HTML 内嵌完整许可信息，不占正文版面。

家庭输入、私有配置和独立报告正文不会因为使用技能而自动公开或适用 MIT；HTML 中复制的模板和库代码仍附带相应许可。反馈问题时请使用虚构或充分匿名化的材料。

## 本次维护更新（2026-10-18）

视觉版本 `2.1.2`：加深小号橙色信息文字及编号，保留原有布局、正文和装饰配色。公开示例已使用当前构建器重新生成。源码与自动化测试不能代替真实浏览器和导出文件的视觉验收。

家庭会议新增审计交付检查：固定“原话或观点定位／校准与可用表达”表头，区分原话与概括并记录说话人、定位。`deliver_report.py finish` 缺项即停止构建与归档。详见 [证据约定](references/weekly.md#审计表与证据约定)；低层构建器仍可无损渲染旧文，但不代替正式交付检查。
