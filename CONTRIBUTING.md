# 三人协作约定

1. 默认分支 `main` 保持可用。除首次初始化外，日常修改建议走分支和 Pull Request。
2. 分支命名：`docs/xxx`、`feat/xxx`、`fix/xxx`，例如 `docs/organizer-interview`。
3. 提交信息写清做了什么，例如 `docs: add technology survey`。
4. PR 至少请另一位同学阅读，必要时写明实际验证方法；文档没有校对不要声称已审核。
5. 与业务规则有关的变更，先更新需求文档或注明尚待确认。
6. 不要提交 `.env`、API Key、GitHub Token、密码、个人配置和隐私数据。
7. 每次开始工作先 `git pull` 更新本地；遇到冲突先沟通再处理。

## 新成员首次操作

```bash
git clone https://github.com/w2ncf666/campus-event-manager.git
cd campus-event-manager
git switch -c docs/your-name-setup
# 编辑你的文档，确认变更后：
git add docs/team-environment.md
git commit -m "docs: add my setup notes"
git push -u origin docs/your-name-setup
```

随后到 GitHub 仓库页面发起 Pull Request。
