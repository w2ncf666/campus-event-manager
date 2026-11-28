# 现场模块复验与手机测速

## 已复验的功能

复验版本为 [PR #6 的 `2c46d6c`](https://github.com/w2ncf666/campus-event-manager/commit/2c46d6ce52c44d919f53e5eb46185954134bb660)，公共迁移基线为 `7b636dd`。2026 年 11 月 28 日跑完 MySQL 8.4.13/InnoDB 的迁移检查和 42 项测试。用例以模拟人员和时钟执行。 [GitHub CI 原始日志](https://github.com/w2ncf666/campus-event-manager/actions/runs/46113507970/job/140882069852)

| 用例 | 操作 | 复验结果 |
| --- | --- | --- |
| AC-07 候补确认 | A 在 13:29:59 接受邀请，签到岗刷新名单 | 显示 A，A 仍占原预留席。重复签到只记一次。 |
| AC-07 到期与现场接管 | B 的留位在 13:30 到期，14:00 开场后登记在场并补位 | 到期后空席可查，开场前补位被拒，开场后同一次提交占席并签到，重试只记一次。 |
| AC-07 人工释位 | 14:29:59、14:30 分别尝试释放正式未到场者 C | 前者被拒，后者开放一席且仅写一条释位记录。 |
| Excel 联调 | C 被释放并记为阶段缺席，15:01 现场补位，16:00 由财务下载并回读 | 学号 `0003` 只有一行。入场方式为「现场临时」，保留释位理由和阶段缺席，最终结果为「出席」。 |
| Excel 字段复核 | 直接回读出席明细和活动汇总 | 学号前导零保留；报名类别、签到和释位时间可读；按文本写入的特殊输入保持文本；网页和导出复用同一汇总口径。 |

复验用例见 [AC-07 页面串联](../backend/events/test_onsite_views.py) 和 [Excel 回读](../backend/events/test_attendance_report.py)。在 `backend` 下可复跑：

```powershell
python manage.py test events.test_onsite_views.OnsiteViewTests.test_ac07_through_staff_views_and_released_person_export events.test_attendance_report --noinput -v 2
```

## NFR-02 真机计时

目前待测。按 [PRD 移动端验收](../_bmad-output/planning-artifacts/PRD.md) 使用同一测试部署、实体手机、浏览器和 Wi-Fi。脚本创建独立测试活动，包含 70 条正式报名、20 条现场候补和 10 条释位历史，分配给已有的测试签到账号。

在已迁移的测试部署上，从 `backend` 运行：

```powershell
$env:NFR02_STAFF_USERNAME = '替换为已有的测试签到账号'
python -X utf8 manage.py shell -c "import runpy; runpy.run_path('../scripts/seed-onsite-performance.py')"
```

手机登录测试签到账号，从 `/onsite/` 打开脚本输出的活动。预热一次。随后每次回到活动入口，再点击「打开签到」。从点击开始，到首屏可读且签到控件能操作为止。连续测 10 次，可以用手机录屏回看时间。加载失败计超标，至少 9 次在 2.0 秒内才通过。

- 部署提交与时间：待填
- 手机型号、系统、浏览器版本与 Wi-Fi：待填

| 次数 | 秒数或加载失败 | 是否 ≤ 2.0 秒 |
| --- | --- | --- |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |

本机 Django 测试客户端曾对一份 100 人全正式名单预热后运行 10 次，服务端处理和模板输出耗时 23.6–48.6 ms。真机结果使用本节记录。
