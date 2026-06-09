# 工时报工系统 · 内网部署文档

## 架构

```
                    ┌──────────────────────────┐
   浏览器  ───80──▶ │  nginx 机器               │
                    │  /opt/worktime/frontend/dist  (前端静态)
                    │  /worktime-api/ 反代 ──┐  │
                    └────────────────────────┼──┘
                                             │ 轮询
                         ┌───────────────────┴───────────────────┐
                         ▼                                       ▼
              ┌────────────────────┐                ┌────────────────────┐
              │ 后端机器 A :18760    │                │ 后端机器 B :18760    │
              │ /opt/worktime/backend                /opt/worktime/backend
              └─────────┬──────────┘                └─────────┬──────────┘
                        └──────────────┬───────────────────────┘
                                       ▼
                            ┌────────────────────┐
                            │  共享 MySQL         │  chronos 库
                            └────────────────────┘
```

- 两台后端**无状态**：访问令牌由密码算出、业务身份在请求里、数据都在共享 MySQL，所以**任一台都能处理任意请求，nginx 轮询即可，无需会话粘性**。
- **MySQL 必须是两台后端都能连的同一个库**（单独 DB 机器，或装在其中一台、另一台远程连）。不要各连各的 localhost。

## 0. 前置
- 每台后端：Python **3.9.x**（与你内网一致即可）、能连 MySQL。
- MySQL 5.7+/8.0，库 `chronos`（应用首次启动会自动建库建表，也可手动建）。
- nginx 机器：nginx。
- 三台机器**时区都设为 Asia/Shanghai**（见第 4 步）。

---

## 1. 准备 MySQL（一次）
后端用 **root** 直连（env.sh 里配的就是 root），**不需要额外建账号**。库和表后端首次启动会**自动创建**，这步通常可跳过。若想手动建库：
```sql
CREATE DATABASE IF NOT EXISTS chronos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
> 若不想用 root、要建专用账号再执行：`CREATE USER 'worktime'@'%' IDENTIFIED BY '强密码'; GRANT ALL ON chronos.* TO 'worktime'@'%'; FLUSH PRIVILEGES;`，然后把 env.sh 的 `DB_USER`/`DB_PASSWORD` 改成它。
建表：表会在后端首次启动时**自动创建**（含 work_content / avail_normal / avail_overtime 列的自动补齐）。也可用随附的脚本手动建（留档/核对结构用，幂等可重复执行）：
```bash
mysql -u root -p < deploy/schema.sql
```

---

## 2. 部署后端（两台机器各做一遍）
```bash
sudo useradd -r -s /sbin/nologin worktime 2>/dev/null || true
sudo mkdir -p /opt/worktime
# 把项目的 backend/ 目录拷到 /opt/worktime/backend
sudo cp -r backend /opt/worktime/backend
sudo mkdir -p /opt/worktime/backend/logs

# 装依赖（二选一）
# A. 直接用系统 python3.9（无需 venv，control.sh 会自动用 python3.9）：
sudo python3.9 -m pip install -r /opt/worktime/backend/requirements.txt
# B. 或建独立 venv（control.sh 检测到会优先用它）：
#   sudo python3 -m venv /opt/worktime/venv
#   sudo /opt/worktime/venv/bin/pip install -r /opt/worktime/backend/requirements.txt
# 若 python3.9 不在 PATH，在 env.sh 里设 PYTHON_BIN=/具体/路径/python3.9

# 配置 DB/端口/门禁密码：拷 env.sh 填真实值（不改代码、密码不进代码库）
sudo cp deploy/env.sh.example /opt/worktime/backend/env.sh
sudo vi /opt/worktime/backend/env.sh
```
`env.sh`（KEY=value 格式，control.sh 与 systemd 都会自动加载）：
```sh
DB_HOST=<your-db-host>    # 共享 MySQL 的 IP（不要写 localhost）
DB_PORT=3306
DB_USER=root
DB_PASSWORD=<your-db-password>     # 改成真实密码
DB_NAME=chronos
APP_PORT=18760
ACCESS_PASSWORD=<改成你们的登录密码>
TZ=Asia/Shanghai
```
> 不设 env.sh 时 config.py 默认连 localhost（仅本地开发）。生产务必拷 env.sh 填真实值，密码不会进代码库。
启动（二选一）：

**方式 A（推荐，和 afhm 其它服务一致，不需要 root）—— control.sh + cron 看门狗**
```bash
sudo mkdir -p /opt/worktime/backend/bin
sudo cp deploy/control.sh /opt/worktime/backend/bin/control.sh
sudo chmod +x /opt/worktime/backend/bin/control.sh
sudo chown -R worktime:worktime /opt/worktime
# 用运行账号执行（cron 看门狗会装到该账号下）
sudo -u worktime sh /opt/worktime/backend/bin/control.sh start
sudo -u worktime sh /opt/worktime/backend/bin/control.sh status
# 用法： start | stop | restart | status；start 会自动加每2分钟的看门狗 cron，挂了自动拉起
```

**方式 B（可选，有 root 且想要崩溃秒级重启 + 开机自启）—— systemd**
```bash
sudo cp deploy/worktime-backend.service /etc/systemd/system/
sudo chown -R worktime:worktime /opt/worktime
sudo systemctl daemon-reload
sudo systemctl enable --now worktime-backend
systemctl status worktime-backend
```
> 两种**别同时用**（会互相抢 18760 端口/PID）。选 A 就别 enable systemd，选 B 就别跑 control.sh。

验证后端起来了：
```bash
curl -s http://127.0.0.1:18760/worktime-api/records?username=x   # 返回 401（未登录）= 正常
```

---

## 3. 部署前端 + nginx（nginx 机器）
前端已打包好（`frontend/dist/`，API 用相对路径，自动走 nginx 反代）。
```bash
sudo mkdir -p /opt/worktime/frontend
sudo cp -r frontend/dist /opt/worktime/frontend/dist

# 安装 nginx 配置，把里面两台后端 IP 改成真实地址
sudo cp deploy/nginx.worktime.conf /etc/nginx/conf.d/worktime.conf
sudo vi /etc/nginx/conf.d/worktime.conf      # 改 upstream 里的两台后端 IP 占位符

sudo nginx -t && sudo systemctl reload nginx
```
> 若前端代码有改动需重新打包：在有 node 的机器上 `cd frontend && npm install && npm run build`，再把 `dist/` 拷过去。

---

## 4. 时区（重要！）
报工的时间戳按**东八区**算。后端 systemd 已带 `Environment=TZ=Asia/Shanghai`；建议三台系统时区也设上海：
```bash
sudo timedatectl set-timezone Asia/Shanghai
timedatectl                      # 确认 Time zone: Asia/Shanghai
```
- 有 NTP 很好（保证时刻准），但 **NTP 不管时区**，时区必须单独设。
- 「全选本周」的"今天"取的是**用户浏览器**时钟，确保用户电脑时间也正常（一般域内机器走 NTP 即可）。

---

## 5. 验证
1. 浏览器打开 `http://<nginx机器IP>/` → 出现登录页。
2. 用 `admin / 你设的密码` 登录。
3. 「认证配置」粘贴 reportWorkingHours 的 cURL → 保存（显示真实用户名）。
4. 日历选天 → 生成待填报 → 记录页微调 → 勾选提交。
5. 关掉其中一台后端，系统仍可用（nginx 自动切到另一台）= 双机生效。

---

## 6. 日志（排查用）
后端机器 `/opt/worktime/backend/logs/`：
- `app.log`：全部业务/接口日志（每天轮询，留 30 天）
- `error.log`：仅错误
- `report_audit.log`：**报工审计** —— 每条提交一行（用户/日期/正常/加班/结果/服务器返回），留 90 天。出问题先看这个。
- `service.out.log` / `service.err.log`：systemd 进程输出

例（report_audit.log）：
```
2026-06-05 16:01:34 REPORT user=<your-user-id> date=2026-06-05 normal=8.0 overtime=0.0 result=success msg=
2026-06-05 16:01:43 REPORT user=<your-user-id> date=2026-06-08 normal=8.5 overtime=0.0 result=failed msg=400 填报工时大于8小时，请确认!
```

---

## 7. 注意事项 / 已知项
- **认证信息是明文存 MySQL 的**（user_configs 表）。内网内部工具可接受；如需更严，可后续加密存储。
- **原系统 token 会过期**：过期后查询/提交会失败，让用户重新抓一条 reportWorkingHours 的 cURL 重新保存即可。
- **改登录密码**：改各后端 `config.py` 的 `ACCESS_PASSWORD` 后 `systemctl restart worktime-backend`，所有人需重新登录。
- 查询/提交对原系统的调用已改为**线程池异步**（不阻塞事件循环），多人并发不会互相卡死；但单次提交仍是逐条顺序发，批量很大时耗时较长（nginx 超时已放宽到 300s）。
