# Django 公共数据与候补服务

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

上述接口由服务端调用。参与者 ID 来自已核验的本人会话，工作人员 ID 来自已登录账号。首次发出的邀请失效时点由活动配置决定，重发保留原时点和冷却状态。页面、本人会话签发与现场操作由各模块接入。

## 联调用例

- 容量 16、15 席已确认、1 席有效留位时提交新报名，结果为候补。
- 候补待确认时退出并在报名截止前重报，参与者 ID 保持一致。旧报名和邀请可追溯，旧凭证无法确认新轮次。
- 11:50 发出的示例邀请在 13:29:59 接受后出现在共享名单。另一条未确认留位 13:30 起可从共享查询读为空位，供现场模块开场后使用。
- 用两个独立数据库连接争最后一席时，先取得序号者确认，另一人排队。另测两条邀请争同一席，以及接受与退出同时发生。
