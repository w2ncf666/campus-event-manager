# BMAD 6.12.4 安装与验证

项目准备阶段采用原模板列出的 **BMAD 6.12.4**，本机以 **Codex + BMad Method（BMM，包含 Core）**验证。如课程要求指定版本，三人按课程要求统一。安装器需要 Node.js 20.12 或更新版本。BMAD 的帮助和部分其他工作流通过 `uv` 运行 Python 脚本。

## 在仓库根目录安装

Windows PowerShell：

```powershell
node --version
npm.cmd --version
uv --version
npx.cmd --yes bmad-method@6.12.4 install --yes --modules bmm --tools codex --user-name campus-event-team --communication-language "Simplified Chinese" --document-output-language "Simplified Chinese" --output-folder _bmad-output
```

在 macOS 或 Linux 上，使用 `npm` 和 `npx`。如使用其他 AI 工具，可运行交互式安装 `npx bmad-method@6.12.4 install`，选择 BMad Method 和实际使用的工具，将交流与文档语言设为简体中文，输出目录设为 `_bmad-output`。Windows PowerShell 使用 `npx.cmd`。

[BMAD v6.12 官方安装说明](https://github.com/bmad-code-org/BMAD-METHOD/blob/V6.12/docs/start/install-bmad.md) · [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)

## 打开项目并调用帮助

1. 在 Codex 里打开克隆的 `campus-event-manager` 文件夹。
2. 在新对话输入 `$bmad-help`，询问当前可以使用哪些规划工作流。
3. 将实际工具、版本和结果填到[三人环境登记表](team-environment.md)。

BMAD 为 Codex 生成 `_bmad/` 和 `.agents/skills/bmad-*/`，每位组员可以按本页命令在本机重建。需要共同维护的规划文档可提交到 `_bmad-output/planning-artifacts/`。 [Codex 技能说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)

## 和课程流程衔接

收到访谈记录和课程要求后，依次使用 `bmad-product-brief`、`bmad-prd`、`bmad-architecture`、`bmad-create-epics-and-stories` 和 `bmad-sprint-planning`。开发和评审使用 `bmad-build` 与 `bmad-code-review`。本项目安装的 `bmad-help` 可查询各工作流的用途和前置步骤。
