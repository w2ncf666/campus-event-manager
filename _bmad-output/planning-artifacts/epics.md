---
status: approved
source_prd: "v0.2"
source_architecture: "PR #4"
---

# 社团活动报名与候补系统史诗与故事

以 [PRD v0.2](PRD.md) 和[架构定稿](architecture.md)为基线。三类业务分工保持一致，候补邀请负责人先牵头公共迁移。组内架构评审及课堂 M1、M2 均已通过，按下列故事分批实施。按 [AC-07 候补与现场交接](PRD.md#4-功能验收) 联合验收。

## 可测非功能需求

- **NFR-01 名额一致性**对应 AC-01。在 MySQL/InnoDB 上用独立连接争抢最后一席，只分出一席，其余参与者进入候补，同一请求重放不增加有效报名。
- **NFR-02 移动名单性能**对应 PRD 移动端验收。用同一设备、浏览器、Wi-Fi 及部署版本读取 100 条模拟名单，10 次中至少 9 次在 2.0 秒内可操作签到。

## 功能需求覆盖

| 需求 | 对应故事 |
| --- | --- |
| FR-01 | [1.1](stories/1-1-shared-schema.md)、[1.2](stories/1-2-activity-publishing-and-roster-identity.md) |
| FR-02 | [1.1](stories/1-1-shared-schema.md)、[1.3](stories/1-3-limited-signup.md)、[1.4](stories/1-4-withdrawal-and-re-application.md) |
| FR-03 | [1.2](stories/1-2-activity-publishing-and-roster-identity.md)、[1.4](stories/1-4-withdrawal-and-re-application.md) |
| FR-04 | [1.1](stories/1-1-shared-schema.md)、[2.1](stories/2-1-issue-invitation-and-hold-seat.md)、[2.4](stories/2-4-skip-one-vacancy-round.md) |
| FR-05 | [2.2](stories/2-2-respond-and-update-roster.md)、[2.3](stories/2-3-expire-invitation-and-free-hold.md)、[2.5](stories/2-5-reissue-invitation.md) |
| FR-06 | [2.4](stories/2-4-skip-one-vacancy-round.md)、[2.5](stories/2-5-reissue-invitation.md) |
| FR-07 | [1.1](stories/1-1-shared-schema.md)、[2.2](stories/2-2-respond-and-update-roster.md)、[3.1](stories/3-1-check-in-and-late-notes.md) |
| FR-08 | [3.1](stories/3-1-check-in-and-late-notes.md)、[3.3](stories/3-3-release-and-absence.md) |
| FR-09 | [1.1](stories/1-1-shared-schema.md)、[2.3](stories/2-3-expire-invitation-and-free-hold.md)、[3.2](stories/3-2-on-site-admission.md)、[3.3](stories/3-3-release-and-absence.md) |
| FR-10 | [1.1](stories/1-1-shared-schema.md)、[3.4](stories/3-4-counts-and-excel-export.md) |
| FR-11 | [1.1](stories/1-1-shared-schema.md)、[1.2](stories/1-2-activity-publishing-and-roster-identity.md)、[1.3](stories/1-3-limited-signup.md)、[1.4](stories/1-4-withdrawal-and-re-application.md)、[2.1](stories/2-1-issue-invitation-and-hold-seat.md)、[2.2](stories/2-2-respond-and-update-roster.md)、[2.3](stories/2-3-expire-invitation-and-free-hold.md)、[2.4](stories/2-4-skip-one-vacancy-round.md)、[2.5](stories/2-5-reissue-invitation.md)、[3.1](stories/3-1-check-in-and-late-notes.md)、[3.2](stories/3-2-on-site-admission.md)、[3.3](stories/3-3-release-and-absence.md)、[3.4](stories/3-4-counts-and-excel-export.md) |
| FR-12 | [3.3](stories/3-3-release-and-absence.md)、[3.4](stories/3-4-counts-and-excel-export.md) |

## Epic 1: Activity signup

**活动报名**。先建立公共模型，再让参与者能进入指定活动，按共享容量完成报名或加入候补，并查看本人状态。

### Story 1.1: Shared schema

公共模型与迁移。三位模块负责人共同使用一套模型和迁移，活动、名单、席位及历史记录可以互相核对。[故事卡与验收](stories/1-1-shared-schema.md)

需求 FR-01、FR-02、FR-04、FR-07、FR-09、FR-10、FR-11，架构 ADR-002、ADR-003、ADR-004、ADR-005、ADR-006。

### Story 1.2: Activity publishing and roster identity

活动发布与本人身份。活动负责人配置并发布活动，参与者凭本场个人凭证进入同一名单下的本人记录。[故事卡与验收](stories/1-2-activity-publishing-and-roster-identity.md)

前置故事 [1.1](stories/1-1-shared-schema.md)。

需求 FR-01、FR-03、FR-11，架构 ADR-001、ADR-003、ADR-006。

### Story 1.3: Limited signup

限额报名与候补顺序。一席最多分配给一人，额满或有在先候补时按服务端序号排队。[故事卡与验收](stories/1-3-limited-signup.md)

前置故事 [1.2](stories/1-2-activity-publishing-and-roster-identity.md)。

需求 FR-02、FR-11、NFR-01，架构 ADR-002、ADR-003、ADR-004、ADR-006。

### Story 1.4: Withdrawal and re-application

报名退出、重报与本人状态。参与者查看本人状态，并在允许的时间撤回报名或按新顺序重报。[故事卡与验收](stories/1-4-withdrawal-and-re-application.md)

前置故事 [1.3](stories/1-3-limited-signup.md)、[2.1](stories/2-1-issue-invitation-and-hold-seat.md)。

需求 FR-02、FR-03、FR-11，架构 ADR-003、ADR-004、ADR-005、ADR-006。

## Epic 2: Waitlist invitations

**候补邀请**。让负责人按空位和队列发放邀请，正确处理确认、拒绝、到期、按席跳过和重发。

### Story 2.1: Issue invitation and hold seat

按序发邀请并留位。负责人向当前空位最早的合格候补发放专属邀请，后续确认时能准确转换该留位。[故事卡与验收](stories/2-1-issue-invitation-and-hold-seat.md)

前置故事 [1.3](stories/1-3-limited-signup.md)。

需求 FR-04、FR-11，架构 ADR-003、ADR-004、ADR-005、ADR-006。

### Story 2.2: Respond and update roster

响应邀请与正式名单同步。候补本人接受后，同一席位与签到名单立即反映正式占用，拒绝或无权响应保留正确状态。[故事卡与验收](stories/2-2-respond-and-update-roster.md)

前置故事 [2.1](stories/2-1-issue-invitation-and-hold-seat.md)、[1.4](stories/1-4-withdrawal-and-re-application.md)。

需求 FR-05、FR-07、FR-11，架构 ADR-003、ADR-004、ADR-006。

### Story 2.3: Expire invitation and free hold

硬截止解除留位。待确认的邀请一到硬截止就停止占用，给现场留下可用的自然空位。[故事卡与验收](stories/2-3-expire-invitation-and-free-hold.md)

前置故事 [2.1](stories/2-1-issue-invitation-and-hold-seat.md)。

需求 FR-05、FR-09、FR-11，架构 ADR-004、ADR-005。

### Story 2.4: Skip one vacancy round

按空位轮次跳过。负责人可以说明理由跳过当前空位的一名候补，其他空位仍按原序处理。[故事卡与验收](stories/2-4-skip-one-vacancy-round.md)

前置故事 [2.1](stories/2-1-issue-invitation-and-hold-seat.md)、[2.3](stories/2-3-expire-invitation-and-free-hold.md)。

需求 FR-04、FR-06、FR-11，架构 ADR-003、ADR-004、ADR-005。

### Story 2.5: Reissue invitation

作废重发与冷却继承。负责人可在停发前安全更换凭证，同时保留这轮邀请占用的席位和原到期。[故事卡与验收](stories/2-5-reissue-invitation.md)

前置故事 [2.2](stories/2-2-respond-and-update-roster.md)。

需求 FR-05、FR-06、FR-11，架构 ADR-004、ADR-005、ADR-006。

## Epic 3: Check-in and export

**现场与导出**。让签到岗沿用正式名单及有效空位，按规则办理签到和补位，财务以同一身份记录生成 Excel。

### Story 3.1: Check-in and late notes

共享名单签到与晚到留言。签到岗能从共享名单读取最新正式席位，并按时间核对签到和晚到留言。[故事卡与验收](stories/3-1-check-in-and-late-notes.md)

前置故事 [1.2](stories/1-2-activity-publishing-and-roster-identity.md)、[2.2](stories/2-2-respond-and-update-roster.md)。

需求 FR-07、FR-08、FR-11、NFR-02，架构 ADR-001、ADR-003、ADR-006。

### Story 3.2: On-site admission

现场先候补再临时补位。开场后用共享可用席位办理现场补录，确保同一人、同一席位和候补顺序一致。[故事卡与验收](stories/3-2-on-site-admission.md)

前置故事 [2.3](stories/2-3-expire-invitation-and-free-hold.md)、[3.1](stories/3-1-check-in-and-late-notes.md)。

需求 FR-09、FR-11，架构 ADR-003、ADR-004、ADR-005、ADR-006。

### Story 3.3: Release and absence

人工释位与缺席记录。签到岗按规则释放尚未签到的正式席位，阶段缺席与后续入场各自留痕。[故事卡与验收](stories/3-3-release-and-absence.md)

前置故事 [3.1](stories/3-1-check-in-and-late-notes.md)、[3.2](stories/3-2-on-site-admission.md)。

需求 FR-08、FR-09、FR-11、FR-12，架构 ADR-003、ADR-004、ADR-006。

### Story 3.4: Counts and Excel export

出席汇总与 Excel 导出。让授权财务从同一份实际出席数据读取汇总，得到可追溯且去重的 Excel。[故事卡与验收](stories/3-4-counts-and-excel-export.md)

前置故事 [3.2](stories/3-2-on-site-admission.md)、[3.3](stories/3-3-release-and-absence.md)。

需求 FR-10、FR-11、FR-12，架构 ADR-003、ADR-006。

## 两个冲刺的目标

| 冲刺 | 拟安排的故事 | 检查结果 |
| --- | --- | --- |
| 冲刺 1 | 1.1–1.4，2.1–2.3，3.1 | 先由候补邀请负责人提交共用模型和初始迁移。报名完成名额竞争和退出，候补确认后签到岗可读取正式名单。M3 准备核心流程的可运行演示。 |
| 冲刺 2 | 2.4–2.5，3.2–3.4 | 完成按空位跳过、重发、现场补录、释放与导出。按当前需求补齐联调与 NFR 证据。 |

按实际开发、评审和验收更新冲刺状态。实验 A 的两条故事在实验开始前选择难度相当且尚未实现的项目。据组员转述，老师确认本次继续按现有需求完成项目，实验 B 免做，截止前提交 GitHub 仓库链接。
