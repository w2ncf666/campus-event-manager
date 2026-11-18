# 小组项目上手指南

## 1. 加入课程仓库

课程仓库已建立，默认分支为 `main`。仓库负责人收集另外两位同学的 GitHub 用户名，在 [Settings → Collaborators](https://github.com/w2ncf666/campus-event-manager/settings/access) 里点击 **Add people**，逐一发送邀请。组员登录对应账号，在 GitHub 通知或邮件里接受邀请。

[课程仓库](https://github.com/w2ncf666/campus-event-manager) · [GitHub 邀请说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)

## 2. 克隆并检查环境

```bash
git clone https://github.com/w2ncf666/campus-event-manager.git
cd campus-event-manager
git status
```

Windows PowerShell：

```powershell
powershell -NoProfile -File .\scripts\check-env.ps1
```

macOS、Linux 和 Git Bash：

```bash
bash scripts/check-env.sh
```

脚本检查命令能否运行，并将结果写到本地 `docs/environment-report.local.md`。按 [BMAD 安装说明](bmad-guide.md)安装并调用帮助技能后，把版本、使用的 AI 工具和运行结果填到[三人环境登记表](team-environment.md)，同时填写熟悉的语言、框架和数据库。

## 3. 验证可协作

两位组员可以各自从 `main` 开分支，把自己的环境登记或负责的项目文档作为首次 PR。只暂存本次修改的文件，详细流程见[协作约定](../CONTRIBUTING.md)。仓库负责人在[准备进度](repository-status.md)记录邀请接受情况和验证结果。
