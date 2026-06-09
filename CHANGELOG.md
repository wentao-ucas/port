# 更新日志（工时报工系统）

> 由三个脚本（generate_mytime / get_data_work_time / single_port）产品化而来的 Vue3 + Tornado + MySQL 工时报工系统。目标系统：`xiaokong.cfid.cn`（效控平台）。

## 2026-06-09（超期判定：记录绑任务快照）

### 工时记录 / 超期（数据模型改动）
- **记录绑任务快照**：`work_records` 新增 4 个可空列 `task_id / task_name / plan_start / plan_end`（启动 `ensure_workrecord_task_columns()` 自动迁移）。生成待填报时由前端把「本次报工任务」的 id/名/计划周期一起传给 `fill-draft`，后端盖到每条记录上（重新生成同一天会重新盖章为当前任务）。
- **超期改按"记录自己的周期"判**：前端 `isRecOutOfRange(rec)` 用记录自带的 `plan_start/plan_end` 与 `work_date` 比，**与当前配置无关**。解决两个老问题：① 完整模式以前拿不到周期判不出超期；② **换到别的任务后，历史里以前的记录被按新任务周期"假标超期"**——现在历史按各自盖章的任务周期判，不再误标。
- **旧记录安全降级**：迁移前的历史记录这 4 列为 NULL → 无法判 → 不显示超期、任务列显示「—」（无法可靠还原其当初任务，不回填）。
- **日期比较用整数**：`dateToNum("Y-M-D")` 解析成 `YYYYMMDD` 整数再比，补不补零都对、不靠字符串比大小，格式异常一律按"不超期"安全降级。
- **历史 tab 加「任务」列**：显示每条记录所属任务名；超期红标两个 tab 都显示（绑任务后历史超期是真实可靠的）。
- **未动 `gstbRwjz`**：完整模式提交体的 gstbRwjz 仍沿用原值（本次只做显示层绑定，不改提交体）。
- 浏览器端到端验证（两种模式 + 旧数据）：完整模式真·日历生成→记录盖章正确；换任务后历史按各自周期判（在内的不误标、超期的如实标）；待处理按当前任务判；旧 NULL 记录不标、任务列「—」；懒人模式盖章取自模板 `_jh*`、超期正确。

## 2026-06-08（提交并发 / 安全 / 体验修复 / 后端模块化）

### 提交报工
- **提交并发化**：原逐条串行 + 每条 `sleep(0.5)` → `asyncio.gather + Semaphore(5)`（DB 串行取写、网络并发）；5 条约 8.5s → ~1-2s。前端「提交所选」改逐条并发 + **提交进度弹窗**（逐条 ✓/✗ + 进度条）。
- **工作内容传空修复**：`SubmitHandler` 原只覆盖工时/日期、漏 `gstbGzbg`（懒人模板里它是空）→ 抽出 `build_submit_data`，工作内容按 记录→模板→默认 三级回退（完整模式下记录页改的内容也真正发出去了）。
- **超期软拦截**：报工日期超出任务计划周期 `[jhKsDate,jhJsDate]` → 记录页标红「超期」+ 提交前弹窗列出、确认后仍可提交（仅懒人模式有周期信息）。

### 安全 / 认证
- **门禁令牌 24h 有效期**：原 `sha256(账号:密码:盐)` 固定常量永不过期 → 改 `base64(签发时间戳.HMAC)`，超 `ACCESS_TTL=24h` 需重登（前端 401 自动回登录页）。**部署后旧令牌全失效，所有人需重登一次。**
- **退出彻底清空**：`logoutAll` 补清 config/parsedInfo/内存缓存/懒人字段，杜绝同浏览器换人后看到上一个人的 curl/token。
- **同浏览器切 curl 防串数据**：`setUser` 换身份时清 monthCache/tasks/records 等。
- **认证失效明确提示**：保存/测试配置后实测一次，token 失效（上游"登录过期"）→ 弹「认证失效，请重新抓取 curl」并留在配置页；「我的任务」遇登录过期同样提示。

### 配置
- **粘错防呆**：完整模式粘成 "Copy all as cURL"（多条请求）或无有效 `--data-raw` → 拒绝保存并提示「只复制单条 reportWorkingHours 的 Copy as cURL」。
- **「测试配置」修复**：原保存前点测试因无身份假失败 → 改"先存后测"；`parseCurlCommand` 解析新 curl 先清旧值（不再残留上一条的"已识别"/旧预览）。
- **user_configs 加 `display_name`（英文名）列**：存 token 的 user_name，启动 `ensure_display_name_column()` 自动建列 + 从 authorization 回填已有行。

### 工时记录
- **本次报工任务条**：记录页顶部显示 任务名/项目名/状态/计划周期（按 gstbRwId 匹配 getMyTask），两种模式通用。
- **跨页全选**：表头全选只选本页 → 加「全选全部 (N)」「清空选择」+ 选择列 `reserve-selection` 跨页保留；删除/提交后清掉勾选（避免残留计数）。
- **换任务防呆**：同用户换任务且有待提交 → 弹「清空并切换 / 取消」，保证待提交永远属当前任务（否则旧任务待提交会被算到新任务名下）。

### 后端结构
- **handlers 模块化**：1272 行 `app.py` 的 15 个 Handler 拆到 `backend/handlers/`（base/auth/config/records/excel/worktime/tasks + common 公共件），`app.py` 只留路由 + 启动。**零行为变化**（AST 精确切片保证字节一致 + 全功能验证）。

### 其它
- 新增 **favicon**（赭色时钟），原浏览器标签页无图标。
- 排查脚本（均本地用、**不部署**）：`check_configs.py`（配置体检，`--live` 实测 token）、`verify_modes.py`、`verify_config_validation.py`、`run_smoke.py`、`test_submit_concurrency.py`。
- **懒人模式提交体经 2 条真实样本 × 两模式逐字段对账**：19 字段全一致、`gstbGzlx/gstbRwzt/type` 等常量跨任务恒定、`freeapproveruserid/gstbTbrq` 留空正确。

## 2026-06-07（增强与上线准备）

### 配置与部署
- **DB 配置环境变量化**：`config.py` 改环境变量优先（本地默认 localhost，生产用 `deploy/env.sh`，密码不进代码）；新增 `env.sh.example`，`control.sh`/systemd 自动加载。
- **库名 `chronos`**（原 worktime_system）；**后端端口 18760**（原 8888，避开常见端口）。
- **nginx 独立端口**：目标机 80/8080/8088 已被其它服务占用，worktime 用独立端口（如 18761）放 `conf.d/`，与现有服务隔离、不动主配置。
- `schema.sql`/DEPLOY 去掉多余建账号（root 直连即可）；库表后端首启自动建。
- **control.sh**：自动定位 app.py（支持放 `backend/bin/`）、自动加载 `env.sh`、用系统 `python3.9`（`PYTHON_BIN` 可覆盖）；部署结构 `backend/bin/control.sh` + `backend/env.sh`。
- **依赖**：固定 `SQLAlchemy==2.0.23`（部署机原装 1.4 缺 `async_sessionmaker`，要装 2.0.23）；可用系统 python3.9 直接 `pip install`，不强制 venv。

### 性能（上线后优化）
- **query-worktime 并发化**：原逐天串行调 xiaokong + 每天 `sleep(0.2)`，一个月 ~40s → 改 `asyncio.gather + Semaphore(8)`、去 sleep，降到 **~5s**（xiaokong 吞吐 ~6.5 req/s 物理上限，gather 保序）。
- **前端按月内存缓存**（`monthCache`）：翻过的月份翻回**瞬时**不重查；刷新页面清空、提交报工后失效、「刷新本月」强制重查。

### 新功能
- **「我的任务」页**：调 `getMyTask` 拉填报任务，四状态排序（进行中>未开始>已暂停>已完成）+ 分页 + 状态筛选。
- **认证懒人模式**：粘任意认证 curl + 选任务 → 后端按已知字段规律自动合成 `template_data`，等价配好 reportWorkingHours；带「开启确认 + 风险提示」，默认完整模式。
- **认证过期提醒**：解析 JWT `exp`，前端顶部横幅（已过期红 / 剩<2h 黄）。

### 体验
- **工时记录分页**：状态下拉改成「待处理(pending+failed) / 历史记录(submitted)」两 tab，历史只读 + 分页；导航徽章=待处理数。
- **日历拖选**：按住鼠标拖动滑选多天（起点决定选中/取消，只对可填的天生效）；新增年月跳转选择器。

### 字段规律（懒人模式的依据）
- 提交报工 `gstbGzlx`/`gstbRwzt`/`type` 实测跨用户/项目/任务**全局固定**；`gstbRwjz` = 报工日是否落在任务计划期 `[jhKsDate,jhJsDate]` 内（1/0），提交时按报工日算。

### 清理
- 删死接口 `GenerateRecordsHandler`(/generate)；文档 `/api/`→`/worktime-api/`、删 generate 引用；补 2022-2025 历史节假日（holidays.js）。

### 工具/演示
- 排查脚本：`test_auth.py`(认证自测)、`benchmark_worktime.py`(性能)、`concurrency_sweep.py`(并发)、`probe_rwjz.py`(字段探查)、`seed_demo.py`(本地演示数据)。
- 身份方案：商量过「工号+各自密码登录」，因登录名可能与 curl 真实身份脱钩（demo_user 登录却粘 demo_user2 的 curl 会报到 demo_user2 头上），**最终决定保持现状**：admin 共享门禁 + curl 的 token `user_id` 定身份。

## 2026-06（本轮重构）

### 登录与多用户
- 新增**全局登录门禁**：账号密码（通过环境变量 `ACCESS_USER/ACCESS_PASSWORD` 配置，见 `backend/config.py` 与 `deploy/env.sh.example`），登录下发 `X-Access-Token`，前端存 localStorage、所有请求带上；后端 `BaseHandler.prepare` 校验，未登录所有数据接口返回 401（挡安全扫描/路人）。导出等用 `?access=` 查询参数。
- **多用户隔离**：从 curl 的 Authorization(JWT) 解析 `user_id` 作隔离键、`user_name` 作显示名（零登录自动识别），各人数据互不可见。

### 可报工时日历（填报主入口）
- 配置好后**默认进日历、自动加载当月可报工时**（逐日调 getInitMsg），翻月自动重查。
- **查询范围内所有日期**（含周末/节假日），周末/节假日有可报工时则可手动选（加班）。
- 选择规则：**全选本周 / 全选本月只挑正常工作日**（跳过周末和法定节假日，调休补班算工作日）；**手动点可选任意有可填工时的天**（含周末/节假日加班）。选择**跨月累加**（翻月不清空）。
- **2026 法定节假日**上历（`frontend/src/holidays.js`，国务院办公厅 2025-11-04 公布），格子标“节/班”。
- 点选后「生成待填报」→ 走 `/worktime-api/fill-draft`：按每天可报工时**写库为 pending 草稿（不提交）**，工作内容取自 curl 模板的 gstbGzbg、没有则用 `DEFAULT_WORK_CONTENT`（默认“日常开发工作”），然后跳到工时记录页。

### 工时记录页
- **列内联编辑**：正常工时、加班工时、工作内容，改完即存（`PUT /worktime-api/records`）。
- **工时上限**：单项封顶 8 小时，且不超过当天“可填上限”（`avail_normal/avail_overtime`，生成草稿时写入），不小于 0；前端 `:max=min(8,avail)`、后端再校验兜底。
- **批量改整列**：正常/加班/内容各一个“应用”（`POST /worktime-api/records/batch`），工时按 `min(值, 8, 当天上限)` 自动封顶；作用于当前筛选出的记录。
- **状态筛选**：全部 / 待提交 / 已提交 / 提交失败（兼当“待填报/历史”分开看）。
- **删除**：单条 + 删除所选（`DELETE /worktime-api/records`，仅删本地 MySQL，不影响已提交到原系统的数据）。
- **统计实时**：正常/加班/总工时/人天(÷8)/人月(÷21.75) 随列内编辑即时更新。
- **失败补提交**：筛“提交失败”→ 勾选 → 再次“提交所选”。

### 提交
- **提交成功判定**改为看响应体业务 code（`code==200/0` 或 `success==true` 才算成功，否则记失败并存原因），不再只看 HTTP 200；前端提交后弹框列出失败日期+原因。（真实响应：成功 `{"code":200,"msg":"填报成功!"}`，失败 `{"code":400,"msg":"填报工时大于8小时，请确认!"}`。）
- 每条提交写**审计日志** `backend/logs/report_audit.log`（用户/日期/工时/结果/服务器msg，留90天）。

### 性能与正确性
- **查询/提交改异步**：对 `xiaokong` 的 `requests` 调用用 `asyncio.to_thread` 包装，不阻塞 Tornado 事件循环（多人并发不互相卡）。
- **时间戳显式东八区**：`date_to_ms()` 按 Asia/Shanghai 计算 `gstbBgsj`，避免服务器 UTC 时区导致日期错位。

### UI
- 整体改为 **Claude 暖色风**（奶油底 #f4f2ec + 赤陶珊瑚 #d97757 + 暖炭侧栏），Element Plus 主题用 CSS 变量覆盖；左侧深色侧边栏三视图（可报工时日历 / 工时记录 / 认证配置）。参考 `D:\code\alarm-ai-service\frontend` 与 frontend-design 技能。

### 部署
- 前端 `npm run build` → `frontend/dist`（生产用相对路径，nginx 反代）。
- `deploy/`：`DEPLOY.md`（/opt/worktime、共享MySQL、双机无状态轮询、启动二选一）、`schema.sql`（建库建表）、`control.sh`（**推荐**：nohup+PID+crontab看门狗，与 afhm 其它服务一致、不需root、TZ=Asia/Shanghai、stop 先撤cron再kill）、`worktime-backend.service`（systemd，可选）、`nginx.worktime.conf`（两后端 upstream + 静态dist）。

### 修复
- Windows GBK 控制台 emoji `print` 导致启动崩溃 → 入口重配 stdout/stderr 为 UTF-8（并清掉了代码里所有 emoji）。
- 前端调 `/worktime-api/query-worktime` 但后端无此路由（查询功能整个不可用）→ 补上 `QueryWorktimeHandler`。
- `loadConfig` 乱码、提交结果取值不匹配、导出写死 default_user 等若干前端 bug。

### 本地调试开关
- `WT_MOCK=1` 环境变量：查询返回假“可报工时”（含周末），方便没内网时点日历。**生产绝不要设**（默认关），`deploy/` 的启动脚本都没设。

---

## 1.0（产品化之前）
- 原始三脚本：`generate_mytime.py`（生成工作日列表）、`get_data_work_time.py`（查可报工时）、`single_port.py`（批量提交报工）。
