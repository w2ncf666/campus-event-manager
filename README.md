# 社团活动报名与候补系统

三人课程小组项目。11 月 23 日组内确认以 PRD v0.2 为架构设计和故事拆分的基线，并修订候补跳过规则。

负责人发布活动并设置报名时间和名额。学生可以报名、查看结果和取消报名，满员后进入候补。活动当天由签到岗登记签到和现场补录，财务按权限导出名单。

| 首版范围 | 功能 |
| --- | --- |
| 活动管理 | 配置并发布活动，设置名额和报名截止 |
| 报名与候补 | 报名、查看结果、取消报名、满额候补和递补 |
| 签到与统计 | 登记签到、查看到场名单、统计报名与出席、导出名单 |

活动容量由组织者设置。PRD 用 16 人场次演示候补、现场补位和导出规则。首版暂不纳入支付、短信通知和学校统一登录。

## 首版需求与决议

- [产品简述](_bmad-output/planning-artifacts/product-brief.md)
- [PRD v0.2](_bmad-output/planning-artifacts/PRD.md)
- [组会决议与分工](_bmad-output/planning-artifacts/组会决议与分工.md)

文档保留模拟评审结果，并记录 11 月 23 日确认的候补规则、三人分工和验收条件。系统实现后按 PRD 验证。

## 开发与课程提交

- [架构与共用名单](_bmad-output/planning-artifacts/architecture.md)
- [后端迁移、测试与接入](backend/README.md)
- [史诗与可验收故事](_bmad-output/planning-artifacts/epics.md)
- [项目规约](_bmad-output/planning-artifacts/project-context.md)
- [冲刺状态](_bmad-output/implementation-artifacts/sprint-status.yaml)
- [课程人机决策日志](decision-log.md)

课程 M1（PRD 评审）和 M2（架构答辩）均已通过，现已进入开发。据组员转述，老师确认本次按现有需求继续实施，实验 B 免做，截止前提交本仓库的 GitHub 链接。按 [PR #3 的交接用例](https://github.com/w2ncf666/campus-event-manager/pull/3)走查候补确认、到期与现场补位。

## 开始协作

1. 接受仓库邀请，然后按[小组项目上手指南](docs/setup-guide.md)克隆仓库并检查本机环境。
2. 按 [BMAD 安装说明](docs/bmad-guide.md)安装 BMAD 6.12.4，记录实际结果到[三人环境登记表](docs/team-environment.md)。
3. 按 PRD v0.2、共用数据架构和故事顺序实施，先核对公共迁移再并行接入。

[仓库与环境准备进度](docs/repository-status.md) · [协作约定](CONTRIBUTING.md) · [初步范围](docs/initial-scope.md) · [决策记录](docs/decision-log.md)
