# 社团活动报名与候补系统

三人课程小组项目，已完成首版规则的模拟评审，v0.2 为架构设计和故事拆分的基线。

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
- [模拟评审决议与分工](_bmad-output/planning-artifacts/组会决议与分工.md)

三份文档记录六项模拟评审决议、分工建议和验收条件。系统实现后用 PRD 的场景及移动端口径验证。

## 开始协作

1. 接受仓库邀请，然后按[小组项目上手指南](docs/setup-guide.md)克隆仓库并检查本机环境。
2. 按 [BMAD 安装说明](docs/bmad-guide.md)安装 BMAD 6.12.4，记录实际结果到[三人环境登记表](docs/team-environment.md)。
3. 以 PRD v0.2 为基线设计架构和拆分故事。

[仓库与环境准备进度](docs/repository-status.md) · [协作约定](CONTRIBUTING.md) · [初步范围](docs/initial-scope.md) · [决策记录](docs/decision-log.md)
