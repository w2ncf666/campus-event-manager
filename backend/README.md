# Django 公共数据、候补与现场服务

采用 Python 3.14.10、Django 5.2.19、MySQL 8.4.13/InnoDB 和 mysqlclient 2.2.8。

## 迁移与测试

在仓库根目录创建并启用 Python 3.14.10 的虚拟环境，再进入 `backend` 执行以下命令。

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate --noinput
python manage.py migrate --check
python manage.py test --noinput
```

默认使用本地 SQLite，可运行迁移和顺序测试。运行 MySQL 测试时，先准备一个空的开发库，再通过环境变量配置连接。

| 变量 | 内容 |
| --- | --- |
| `DATABASE_ENGINE` | `mysql` |
| `DATABASE_NAME` | 开发库名称 |
| `DATABASE_HOST`、`DATABASE_PORT` | MySQL 地址和端口 |
| `DATABASE_USER`、`DATABASE_PASSWORD` | 本机开发库账号和密码 |

MySQL 测试账号须能创建和清理专用测试库。GitHub Actions 使用独立的 MySQL 8.4.13 服务运行空库迁移和全部测试。涉及行锁的测试在 SQLite 上跳过。

## 共用名单接口

| 模块 | 接入方式 |
| --- | --- |
| 活动和身份 | `Activity` 保存容量和时点。发布时按容量建立 `Seat`，同场核验学号后复用 `Participant`。活动内工作人员岗位通过 `ActivityStaff` 授权。 |
| 报名和退出 | `events.signups.submit_registration` 接收本场已核验的参与者 ID 和本次请求 UUID。重试沿用同一 UUID，重报使用新的 UUID。`withdraw_registration` 针对本轮 `Registration` ID，旧请求重放只返回原轮次。 |
| 候补邀请 | `events.invitations` 提供预览下一位、发出、接受、拒绝、按空位跳过、重发和到期补记。发出时可带上预览的报名 ID 和空位轮次，防止名单刷新前误发给下一位。负责人从发出或重发的结果取得链接标识和六位码。 |
| 签到名单 | `events.seats.seat_assignments(activity_id)` 查询当前占用，接受邀请提交后下次读取可见。`available_seats(activity_id)` 计入有效留位，硬截止一到即可读取空位。 |
| 现场和导出 | 现场服务在 `transaction.atomic()` 内先调用 `lock_activity(activity_id)`，再读取服务端时钟、校验岗位与阶段，使用 `occupy_seat` 或 `release_seat` 操作共用席位。补位占用与 `Attendance` 同事务写入，释位和阶段缺席分别记入 `RosterEvent`。导出用参与者 ID 合并当前签到和历史。 |

上述接口由服务端调用。参与者 ID 来自已核验的本人会话，工作人员 ID 来自已登录账号。首次发出的邀请失效时点由活动配置决定，重发保留原时点和冷却状态。报名和候补页面及本人会话签发由相应模块接入。

## 现场签到与财务入口

在 `backend` 运行 `python manage.py runserver`，打开 `http://127.0.0.1:8000/onsite/`。用 Django 账号登录后可打开被分配岗位的活动。已有活动、名单和岗位可直接复用。独立验证时在测试库使用模拟活动与人员数据，通过 `ActivityStaff` 给对应账号分配 `check_in` 或 `finance` 岗位。

- 签到岗可刷新正式名单、给已到场的正式成员签到、确认晚到留言，并在活动配置的释位时点后手动释放符合条件的席位。当前席位、现场队列和释位记录只显示掩码学号。现场登记时按完整学号和姓名核验，再按队列补位。补位与签到使用同一事务。
- 财务在活动结束后可查看出席汇总并下载 `.xlsx`。网页和文件按同一数据口径统计，每人一行，保留原报名、实际入场、释位和阶段缺席记录。
- `events.0002_record_onsite_departure` 增加现场离场事件。`events.0003_presence_request` 为到场与离场记录请求 UUID，状态修改和去重记录同一事务提交。旧请求重试沿用原 UUID，重新到场从刷新的名单提交新请求。已有活动与名单可直接执行增量迁移。

运行 `python manage.py test events.test_onsite_views --noinput` 可重放 AC-07，从 `13:29:59` 接受邀请，到 `14:00` 补位、`14:30` 人工释位，再到 `16:00` 财务导出。测试使用模拟数据及时间，包含真实 HTTP 登录、CSRF、岗位授权和 Excel 回读。真实手机与 Wi-Fi 的 NFR-02 测试需在组内部署环境记录 10 次实际计时。

2026-11-24 用 Python 3.12.2、Django 5.2.19 和 MySQL 8.4.13/InnoDB 验证空库迁移、无待迁移项及全部 38 项自动化测试通过，含两个独立连接争现场最后一席的用例。SQLite 上 34 项通过，4 项行锁用例跳过。

[AC-07、Excel 复验结果及 NFR-02 手机测速说明](../docs/onsite-validation.md)

## 联调用例

- 容量 16、15 席已确认、1 席有效留位时提交新报名，结果为候补。
- 候补待确认时退出并在报名截止前重报，参与者 ID 保持一致。旧报名和邀请可追溯，旧凭证无法确认新轮次。
- 11:50 发出的示例邀请在 13:29:59 接受后出现在共享名单。另一条未确认留位 13:30 起可从共享查询读为空位，供现场模块开场后使用。
- 用两个独立数据库连接争最后一席时，先取得序号者确认，另一人排队。另测两条邀请争同一席，以及接受与退出同时发生。
