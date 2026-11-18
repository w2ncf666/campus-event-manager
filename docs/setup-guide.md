# 第二项任务：GitHub 仓库与小组环境准备操作指南

## 一、任务验收标准

- [ ] 独立 GitHub 作业仓库已经建立，并能够打开链接
- [ ] 两位组员都已经接受 Collaborator 邀请
- [ ] 所有成员能克隆仓库、拉取与提交修改（至少完成一次协作验证）
- [ ] `docs/team-environment.md` 三行均有真实填写信息
- [ ] 记录成员是否能运行 BMAD（版本、AI 工具和实际运行结果）
- [ ] 把仓库链接及任务结果发到小组

模板已经准备好，但以上在线操作与成员结果均**未自动完成**。

## 二、创建独立 GitHub 仓库

1. 解压 `campus-event-manager-starter.zip`，得到 `campus-event-manager` 文件夹。
2. 登录 GitHub，打开 https://github.com/new 。
3. `Repository name` 填 `campus-event-manager`（名称建议，已有同名仓库时可修改）。
4. `Description` 可以填：`Campus event registration, waitlist and check-in system | BMAD course project`。
5. 推荐先选 `Private`；课程若要求公开，再修改可见性。
6. **不要勾选自动创建 README、.gitignore 或 License**，本模板已经有 README 和 .gitignore，避免首次提交出现冲突。
7. 点击 `Create repository`。创建后复制真实仓库 URL。

## 三、从 Windows 上把模板推送到 GitHub

在 VS Code 打开解压后的 `campus-event-manager` 文件夹，打开 `终端 > 新建终端`（PowerShell）：

```powershell
# 在本文件夹执行；先确认当前确实位于 campus-event-manager 根目录
git --version
git init -b main
git add .
git commit -m "chore: initialize course project workspace"

# 注意将 YOUR_GITHUB_USERNAME 替换为实际 GitHub 用户名
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/campus-event-manager.git
git push -u origin main
```

说明：如果提示 `Author identity unknown`，先设置自己的 Git 身份（替换为本人信息）：

```powershell
git config --global user.name "你的 Git 用户名或姓名"
git config --global user.email "你的 Git 提交邮箱"
```

然后重新执行 `git commit ...`、`git push ...`。GitHub HTTPS 登录应走 Git Credential Manager / 浏览器授权等正规流程；**不要把密码、Token 或私钥提交到仓库或发给组员**。

若仓库名称做了修改，远程 URL 中的名称必须同步修改。若 `origin` 已存在，先执行 `git remote -v` 核对，别盲目覆盖已有仓库。

## 四、邀请另外两位同学

打开仓库主页：`Settings` → 左侧 `Collaborators`（在 Access 区域）→ `Add people`。

依次输入两名同学的**真实 GitHub 用户名**并邀请，提醒他们在邮件或 GitHub 通知中接受邀请。只有**接受后**才算邀请成功。

邀请完成后，填 `docs/repository-status.md` 中的邀请状态和仓库真实链接。

GitHub 官方操作：https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository

## 五、请组员克隆仓库并进行一次协作验证

请每位组员在自己电脑上执行：

```powershell
git clone https://github.com/YOUR_GITHUB_USERNAME/campus-event-manager.git
cd campus-event-manager
git status
```

推荐协作方式：每个人从 `main` 拉出自己的分支，在分支上修改自己负责的文档，Push 后在 GitHub 提交 Pull Request，由另一位同学审阅后合并。

最简单的一次验证：两位组员分别创建 `docs/team-notes/成员名.md`（可以仅写“仓库访问测试成功”和测试日期），提交至各自分支，通过 PR 合并。请不要提交个人 Token、账号密码或不愿公开的隐私信息。

## 六、确认技术栈和环境

每人先填写 `docs/team-environment.md`，技术栈仍**待小组共同确定**，不要在调研前假定必须用某框架。

### Windows 环境检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-env.ps1
```

脚本只检查本机已有命令及版本并生成 `docs/environment-report.local.md`，**不自动安装软件，也不上传数据**。该文件被 `.gitignore` 排除，供本人查看后将需要的结论手动填写进团队调查表。

### Linux/macOS 环境检查

```bash
bash scripts/check-env.sh
```

若 `node`、`npm`、`npx` 不可用，先安装或修复 Node.js LTS，重新打开终端，再检查。Windows 上 `winget` 显示软件已安装，不代表当前终端一定找得到对应命令。

## 七、BMAD 版本与安装位置

为了和课程材料保持一致，建议**三个人统一 BMAD v6.12.x**，本模板以 `6.12.4` 举例（若老师指定别的版本，以老师要求为准）。

**一定要在新建的 `campus-event-manager` 文件夹根目录执行安装**，不要误装到旧作业 `software_homework` 或其他项目里：

```powershell
node -v
npm -v
npx bmad-method@6.12.4 install
```

安装是交互式的：选择实际使用的 AI 编程工具（如 Codex）、按组内约定设置聊天和文档语言、输出目录。实际生成的 BMAD 目录和配置以安装结果为准，不要照抄假设路径。建议确认工具里 `bmad-help` 可运行，并记录版本/命令/运行截图。

**不要先运行 Product Brief 或 PRD 来代替用户访谈。** 等负责人回收真实需求后才执行相应工作流。

BMAD 官方安装说明：https://github.com/bmad-code-org/BMAD-METHOD/blob/main/docs/start/install-bmad.md

## 八、最后交付给小组的材料

1. 仓库真实 URL：`https://github.com/实际用户名/实际仓库名`
2. 邀请结果：两位组员已接受/待接受（截图可选）
3. `docs/team-environment.md`：三人的实际技术偏好与开发环境
4. BMAD 验证记录：版本、安装目录、AI 工具、`bmad-help` 的结果
5. `docs/repository-status.md`：标注完成和待完成情况

**不要把“已建仓库”“已邀请”写成完成，除非实际完成了在线操作。**
