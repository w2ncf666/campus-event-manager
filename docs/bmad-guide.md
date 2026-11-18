# BMAD v6.12.x 协作说明

## 目标

- 课程作业以 BMAD 流程推进，先调研、再文档、后编码。
- 组员尽量统一 BMAD 主版本及同一项目的输出目录约定。
- 每位同学使用自己的 AI 编程工具环境，但提交内容统一放在小组 GitHub 仓库。

## 安装/验证

在**本项目根目录**打开终端：

```powershell
node -v
npm -v
npx bmad-method@6.12.4 install
```

安装器可能询问目标 IDE、语言、配置等。完成后打开对应 AI 编程工具，尝试调用：

```text
bmad-help
```

注意：`bmad-help` 是在支持 BMAD 的 AI 编程工具内调用的工作流/命令，**不是普通 PowerShell 可执行程序**。

在 `docs/team-environment.md` 记录：实际工具、BMAD 版本、安装目录、是否能运行帮助命令。

## 课程工作流（等材料齐全后再执行）

1. `bmad-create-product-brief`：明确项目目标和范围。
2. `bmad-prd`：整理可验收的需求。
3. `bmad-architecture`：记录技术架构与关键决策。
4. `bmad-create-epics-and-stories`：拆分开发任务。
5. `bmad-sprint-planning`：确定迭代计划。
6. `bmad-build` + `bmad-code-review`：开发和评审。
7. `bmad-retrospective`：复盘过程。

各工作流的**实际命令、前置条件和可用性**以本机安装的 `bmad-help` 返回为准。

## 团队维护约定

- 不在 AI 生成内容里填写假访谈、假验收或假运行记录。
- 由仓库负责人确认是否将 `_bmad/` 配置和 `_bmad-output/` 规划产物加入 Git，避免遗漏作业证据；但提交前检查是否有个人隐私、密钥或缓存文件。
- 如果某位成员尚未安装成功，先记录失败原因，不要把其他人的安装成功视作全员通过。
- BMAD v7 有变化，本课程暂按 v6.12.x 组织，以免组内流程混用。

官方资料：https://github.com/bmad-code-org/BMAD-METHOD
