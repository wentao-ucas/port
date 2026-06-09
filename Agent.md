# Agent.md - 工时报工系统项目文档

> **目标**：让任何AI Agent（包括 Claude、GPT、Gemini等）能快速理解整个项目，并在需要修改时迅速定位关键代码。

---

## 📋 项目概览

**项目名称**：工时报工系统 (Work Time Reporting System)  
**版本**：v2.0 (MySQL异步版本)  
**技术栈**：
- **后端**：Python 3.9 + Tornado 6.3.3 + MySQL 5.x + SQLAlchemy 2.0 (aiomysql)
- **前端**：Vue 3.3.4 + Element Plus 2.4.0 + Vite 4.x
- **数据库**：MySQL (chronos)
- **日志**：Rotating File Handler (保留30天)

**核心功能**：
1. 从浏览器复制curl命令自动解析认证信息
2. 根据日期范围从外部API查询实际可报工时
3. 生成工作日记录（自动排除周末）
4. Excel批量导入/导出功能
5. 多用户隔离（按username）
6. 统计计算：总工时 → 人天(÷8) → 人月(÷21.75)
7. 批量提交到外部报工系统

---

## 🏗️ 项目结构

```
d:\code\port\
├── bin/
│   ├── control.sh        # Linux/Mac 控制脚本
│   └── control.bat       # Windows 控制脚本
├── backend/
│   ├── app.py            # 主应用（Tornado handlers）
│   ├── config.py         # 配置文件（数据库连接、端口等）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user_config.py    # 用户配置表模型
│   │   └── work_record.py    # 工时记录表模型
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── db.py            # 数据库连接管理（async_session_maker）
│   │   ├── excel_helper.py  # Excel导入导出
│   │   └── logger.py        # 日志配置（30天轮询）
│   ├── logs/                # 日志目录（git忽略）
│   │   ├── app.log          # 应用日志
│   │   └── error.log        # 错误日志
│   ├── requirements.txt     # Python依赖
│   ├── test_api.py          # API测试脚本
│   ├── check_db.py          # 数据库验证脚本
│   └── test_db_init.py      # 数据库初始化测试
├── frontend/
│   ├── src/
│   │   ├── App.vue          # 主组件（所有页面）
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── Agent.md             # 本文档
```

---

## 🗄️ 数据库设计

### 数据库：`chronos`

### 表1：`user_configs` - 用户配置表

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | INT AUTO_INCREMENT | 主键 | PRIMARY |
| username | VARCHAR(100) | 用户名（隔离标识） | UNIQUE |
| authorization | TEXT | Bearer token | |
| cookie | TEXT | Session Cookie | |
| curl_template | TEXT | 完整curl命令模板 | |
| template_data | JSON | 报工请求模板数据 | |
| created_at | TIMESTAMP | 创建时间 | |
| updated_at | TIMESTAMP | 更新时间 | |

**作用**：存储每个用户的认证信息和curl命令模板，用于后续API调用

### 表2：`work_records` - 工时记录表

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | INT AUTO_INCREMENT | 主键 | PRIMARY |
| username | VARCHAR(100) | 用户名 | INDEX |
| work_date | DATE | 工作日期 | INDEX |
| normal_hours | DECIMAL(5,2) | 正常工时 | |
| overtime_hours | DECIMAL(5,2) | 加班工时 | |
| status | VARCHAR(20) | 状态（pending/submitted/failed） | |
| created_at | TIMESTAMP | 创建时间 | |
| updated_at | TIMESTAMP | 更新时间 | |

**唯一索引**：`UNIQUE(username, work_date)` - 每个用户每天只能有一条记录

---

## 🔌 后端API接口

**Base URL**: `http://localhost:18760`

### 1. 配置管理

#### GET `/worktime-api/config?username=xxx`
- **功能**：获取用户配置
- **参数**：`username` (query, 可选，默认从cookie读取)
- **返回**：
```json
{
  "success": true,
  "config": {
    "curl_template": "...",
    "authorization": "bearer xxx",
    "cookie": "JSESSIONID=xxx"
  },
  "parsed": {
    "authorization": "bearer xxx",
    "cookie": "JSESSIONID=xxx",
    "template_data": { ... }
  }
}
```

#### POST `/worktime-api/config?username=xxx`
- **功能**：保存配置（自动解析curl命令）
- **Body**：
```json
{
  "curl_template": "curl 'http://...' -H 'Authorization: ...' ..."
}
```
- **解析逻辑**：
  - 正则提取 `Authorization` header
  - 正则提取 `Cookie` (-b参数)
  - 正则提取 `--data-raw` 中的JSON
  - 自动保存到 `user_configs` 表

### 2. 生成记录

#### POST `/worktime-api/generate?username=xxx`
- **功能**：根据日期范围生成工时记录
- **Body**：
```json
{
  "start_date": "2025-01-01",
  "end_date": "2025-01-31"
}
```
- **逻辑**：
  1. 遍历日期范围内的所有日期
  2. 过滤掉周末（`weekday() < 5`）
  3. 调用外部API查询实际可报工时
    - API: `http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{timestamp_ms}`
    - Headers: 使用user_config中的authorization和cookie
    - 返回: `{"data": {"ktbGs": 8.0, "ktbJbGs": 2.0}}`
  4. 插入或更新 `work_records` 表
  5. 返回生成的记录数

### 3. 记录管理

#### GET `/worktime-api/records?username=xxx`
- **功能**：获取用户所有记录 + 统计信息
- **返回**：
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "date": "2025-12-01",
      "normal_hours": 8.0,
      "overtime_hours": 2.0,
      "status": "pending",
      "created_at": "2025-12-31 10:00:00"
    }
  ],
  "statistics": {
    "total_normal_hours": 40.0,
    "total_overtime_hours": 10.0,
    "total_hours": 50.0,
    "person_days": 6.25,      // 50 ÷ 8
    "person_months": 0.29     // 6.25 ÷ 21.75
  }
}
```

#### PUT `/worktime-api/records?username=xxx`
- **功能**：更新单条记录
- **Body**：
```json
{
  "id": 1,
  "normal_hours": 9.0,
  "overtime_hours": 1.0
}
```

### 4. Excel导入导出

#### GET `/worktime-api/excel/export?username=xxx`
- **功能**：导出所有记录为Excel
- **返回**：xlsx文件流
- **格式**：
  | ID | 日期 | 星期 | 正常工时 | 加班工时 | 状态 | 创建时间 |
  |----|------|------|----------|----------|------|----------|
  | 1  | 2025-12-01 | 周一 | 8.0 | 2.0 | pending | 2025-12-31 10:00:00 |

#### POST `/worktime-api/excel/import?username=xxx`
- **功能**：从Excel批量更新记录
- **Body**：`multipart/form-data`，字段名 `file`
- **逻辑**：解析xlsx文件，根据ID批量UPDATE

### 5. 提交报工

#### POST `/worktime-api/submit?username=xxx`
- **功能**：批量提交选中记录到外部系统
- **Body**：
```json
{
  "record_ids": [1, 2, 3]
}
```
- **逻辑**：
  1. 遍历每个record_id
  2. 读取record详情
  3. 填充template_data中的字段：
     - `gstbZcgz`: normal_hours
     - `gstbPtjb`: overtime_hours
     - `gstbBgsj`: work_date的timestamp（毫秒）
  4. POST到外部API
  5. 根据返回更新status（submitted/failed）

---

## 🎯 关键代码位置

### 数据库初始化问题修复
**位置**：`backend/app.py` 末尾

**问题**：之前使用 `asyncio.run(main())` 导致事件循环冲突，`async_session_maker` 为None

**解决方案**：
```python
if __name__ == '__main__':
    try:
        # 使用 Tornado 的 IOLoop 运行异步初始化
        tornado.ioloop.IOLoop.current().run_sync(init_and_start)
        # 启动事件循环
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
```

### 日志系统
**位置**：`backend/utils/logger.py`

**关键点**：
- 使用 `TimedRotatingFileHandler`
- `when='midnight'` 每天午夜轮询
- `backupCount=30` 保留30天
- 两个日志文件：`app.log`（所有日志）、`error.log`（仅错误）

**使用示例**：
```python
from utils.logger import logger, log_api_call, log_business, log_error

log_api_call('ConfigHandler', 'POST', {'username': 'test'})
log_business('生成记录', 'test', '生成10条记录')
log_error('ConfigHandler.post', '保存失败', traceback_str)
```

### Excel导入导出
**位置**：`backend/utils/excel_helper.py`

**核心函数**：
- `export_records_to_excel(records)` - 生成xlsx的BytesIO对象
- `import_records_from_excel(excel_file)` - 解析xlsx返回记录列表

**特色**：
- 自动添加星期几标签（周一~周日）
- 表头样式美化（蓝色背景、白色字体、加粗）
- 自动列宽调整

### 多用户隔离
**位置**：`backend/app.py` - `BaseHandler.get_current_user()`

```python
def get_current_user(self):
    """获取当前用户名"""
    username = self.get_argument('username', None)
    if not username:
        username = self.get_cookie('username', 'default_user')
    return username
```

**工作方式**：
1. 优先从query参数读取 `?username=xxx`
2. 其次从cookie读取
3. 默认使用 `default_user`

---

## 🔧 启动和控制

### Linux/Mac启动
```bash
# 赋予执行权限
chmod +x bin/control.sh

# 启动服务
./bin/control.sh start

# 停止服务
./bin/control.sh stop

# 重启服务
./bin/control.sh restart

# 查看状态
./bin/control.sh status

# 查看实时日志
./bin/control.sh logs

# 清理30天前的日志
./bin/control.sh cleanup
```

### Windows启动
```cmd
REM 启动服务
bin\control.bat start

REM 停止服务
bin\control.bat stop

REM 查看状态
bin\control.bat status
```

### 手动启动（开发）
```bash
cd backend
conda activate tornado
python app.py
```

---

## 🐛 常见问题和调试

### 1. 数据库连接失败
**症状**：`Can't connect to MySQL server`

**检查**：
```bash
# 确认MySQL运行
mysql -u root -p

# 检查数据库是否存在
USE chronos;
SHOW TABLES;
```

**配置位置**：`backend/config.py`
```python
DB_CONFIG = {
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),   # 真实密码走环境变量，见 deploy/env.sh.example
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'database': os.environ.get('DB_NAME', 'chronos')
}
```

### 2. async_session_maker is None
**症状**：Handler中出现 `'NoneType' object is not callable`

**原因**：事件循环冲突（使用了asyncio.run）

**解决**：确保 `app.py` 末尾使用 Tornado的IOLoop：
```python
tornado.ioloop.IOLoop.current().run_sync(init_and_start)
tornado.ioloop.IOLoop.current().start()
```

### 3. 外部API认证失败
**症状**：生成记录时返回401/403

**解决**：
1. 重新在浏览器中完成一次报工
2. F12 → Network → 找到 reportWorkingHours 请求
3. Copy as cURL (bash)
4. 粘贴到配置管理页面
5. Token可能会过期，需要定期更新

### 4. 前端无法连接后端
**症状**：Network Error / CORS错误

**检查**：
1. 后端是否启动：`curl http://localhost:18760/worktime-api/config`
2. 前端开发服务器代理配置：`frontend/vite.config.js`
```js
export default {
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:18760',
        changeOrigin: true
      }
    }
  }
}
```

---

## 📝 前端修改要点

### 原版本问题
1. 生成记录使用年月选择，不够灵活
2. 没有Excel导入导出功能
3. 统计信息不完整（缺少人天、人月）

### 需要修改的组件

#### 1. 生成记录页面（el-tab-pane name="generate"）
**修改前**：
```vue
<el-form-item label="年份">
  <el-input-number v-model="generateForm.year" />
</el-form-item>
<el-form-item label="月份">
  <el-input-number v-model="generateForm.month" />
</el-form-item>
```

**修改后**：
```vue
<el-form-item label="开始日期">
  <el-date-picker 
    v-model="generateForm.start_date" 
    type="date"
    value-format="YYYY-MM-DD"
  />
</el-form-item>
<el-form-item label="结束日期">
  <el-date-picker 
    v-model="generateForm.end_date" 
    type="date"
    value-format="YYYY-MM-DD"
  />
</el-form-item>
```

**JS修改**：
```js
// 修改 generateForm
const generateForm = ref({
  start_date: '',
  end_date: ''
})

// 修改 generateRecords 方法
const generateRecords = async () => {
  // 删除：年月计算逻辑
  // 新增：直接传递 start_date 和 end_date
  const res = await axios.post('/worktime-api/generate', {
    start_date: generateForm.value.start_date,
    end_date: generateForm.value.end_date
  })
}
```

#### 2. 报工管理页面 - 添加Excel按钮
**位置**：记录列表上方的按钮区域

**新增按钮**：
```vue
<el-button type="success" @click="exportExcel">
  <el-icon><Download /></el-icon>
  导出Excel
</el-button>
<el-upload
  action="/worktime-api/excel/import"
  :show-file-list="false"
  :on-success="handleImportSuccess"
  accept=".xlsx"
>
  <el-button type="warning">
    <el-icon><Upload /></el-icon>
    导入Excel
  </el-button>
</el-upload>
```

**JS方法**：
```js
const exportExcel = async () => {
  const username = 'default_user'  // 或从cookie/input读取
  window.open(`/worktime-api/excel/export?username=${username}`, '_blank')
}

const handleImportSuccess = (response) => {
  if (response.success) {
    ElMessage.success(response.message)
    loadRecords()
  } else {
    ElMessage.error(response.message)
  }
}
```

#### 3. 统计信息卡片修改
**位置**：el-tab-pane name="records" 底部

**修改前**：
```vue
<el-statistic title="总工时" :value="statistics.total_hours">
  <template #suffix>小时</template>
</el-statistic>
```

**修改后**：
```vue
<el-row :gutter="20">
  <el-col :span="6">
    <el-statistic title="正常工时" :value="statistics.total_normal_hours">
      <template #suffix>小时</template>
    </el-statistic>
  </el-col>
  <el-col :span="6">
    <el-statistic title="加班工时" :value="statistics.total_overtime_hours">
      <template #suffix>小时</template>
    </el-statistic>
  </el-col>
  <el-col :span="6">
    <el-statistic title="总工时" :value="statistics.total_hours">
      <template #suffix>小时</template>
    </el-statistic>
  </el-col>
  <el-col :span="6">
    <el-statistic title="人天" :value="statistics.person_days" />
  </el-col>
  <el-col :span="6">
    <el-statistic title="人月" :value="statistics.person_months" />
  </el-col>
</el-row>
<div style="margin-top: 10px; color: #909399; font-size: 12px;">
  💡 8小时 = 1人天，21.75天 = 1人月
</div>
```

---

## 🚀 部署建议

### 生产环境配置

1. **MySQL优化**
   - 创建生产数据库用户（非root）
   - 开启慢查询日志
   - 定期备份数据库

2. **后端优化**
   - 使用Nginx反向代理
   - 配置supervisor或systemd管理进程
   - 开启日志轮询清理cron任务

3. **前端构建**
```bash
cd frontend
npm run build
# 将 dist/ 目录放到后端可访问的静态文件路径
```

4. **安全加固**
   - 配置HTTPS
   - 添加IP白名单
   - 定期更新依赖包
   - 使用环境变量存储敏感信息（不要硬编码密码）

---

## 📚 技术细节

### SQLAlchemy异步最佳实践

**正确用法**：
```python
async with db.async_session_maker() as session:
    result = await session.execute(select(WorkRecord).where(...))
    records = result.scalars().all()
    await session.commit()
```

**错误用法**：
```python
# ❌ 不要这样做
session = db.async_session_maker()  # 缺少 async with
result = session.execute(...)        # 缺少 await
```

### Tornado与asyncio集成

**关键点**：
- Tornado有自己的IOLoop（基于asyncio）
- 初始化时使用 `IOLoop.current().run_sync()`
- 服务启动使用 `IOLoop.current().start()`
- Handler中直接使用async/await

### 日志轮询实现

**TimedRotatingFileHandler参数**：
- `when='midnight'` - 每天午夜轮询
- `interval=1` - 每1个周期
- `backupCount=30` - 保留30个备份
- `suffix='%Y%m%d'` - 备份文件名格式：`app.log.20251231`

**自动清理**：
```bash
# 添加cron任务（每天凌晨2点清理）
0 2 * * * /path/to/bin/control.sh cleanup
```

---

## 🔍 代码导航索引

如果要修改特定功能，请参考以下快速索引：

| 功能 | 文件位置 | 关键函数/类 |
|------|----------|-------------|
| **认证配置** | backend/app.py | ConfigHandler.post() |
| **curl解析** | backend/app.py | 第100-120行正则表达式 |
| **生成记录** | backend/app.py | GenerateRecordsHandler.post() |
| **外部API调用** | backend/app.py | 第185-210行 requests.get() |
| **记录列表** | backend/app.py | RecordsHandler.get() |
| **记录编辑** | backend/app.py | RecordsHandler.put() |
| **Excel导出** | backend/utils/excel_helper.py | export_records_to_excel() |
| **Excel导入** | backend/utils/excel_helper.py | import_records_from_excel() |
| **批量提交** | backend/app.py | SubmitHandler.post() |
| **统计计算** | backend/app.py | RecordsHandler.get() 第310-320行 |
| **数据库初始化** | backend/utils/db.py | init_db() |
| **日志配置** | backend/utils/logger.py | get_logger() |
| **用户隔离** | backend/app.py | BaseHandler.get_current_user() |
| **前端主组件** | frontend/src/App.vue | 所有Vue组件 |
| **前端API调用** | frontend/src/App.vue | axios方法（第600-750行） |

---

## 📖 典型开发场景

### 场景1：添加新的统计指标
**需求**：在统计中显示"平均每天工时"

**步骤**：
1. 修改 `backend/app.py` → `RecordsHandler.get()`
```python
# 计算平均每天工时
work_days = len([r for r in records if r.status != 'failed'])
avg_hours_per_day = total_hours / work_days if work_days > 0 else 0

statistics = {
    ...
    'avg_hours_per_day': round(avg_hours_per_day, 2)
}
```

2. 修改前端 `frontend/src/App.vue`
```vue
<el-col :span="6">
  <el-statistic title="平均日工时" :value="statistics.avg_hours_per_day">
    <template #suffix>小时/天</template>
  </el-statistic>
</el-col>
```

### 场景2：支持新的外部API
**需求**：切换到新的报工系统API

**步骤**：
1. 修改 `backend/app.py` → `GenerateRecordsHandler.post()`
   - 更新API URL
   - 修改headers格式
   - 调整返回数据解析逻辑

2. 修改 `SubmitHandler.post()`
   - 更新提交API URL
   - 修改请求body格式

### 场景3：添加新的用户字段
**需求**：在用户配置中添加"部门"字段

**步骤**：
1. 修改数据库表
```sql
ALTER TABLE user_configs ADD COLUMN department VARCHAR(100);
```

2. 修改 `backend/models/user_config.py`
```python
class UserConfig(Base):
    ...
    department = Column(String(100))
```

3. 修改 `backend/app.py` → `ConfigHandler`
   - GET方法返回department
   - POST方法保存department

4. 修改前端添加输入框

---

## 🎓 学习路径

**如果你是新的AI Agent接手这个项目**：

1. **第一步**：理解数据流
   ```
   浏览器curl → 配置管理 → 数据库user_configs
   外部API → 生成记录 → 数据库work_records
   工时记录 → Excel导出 → 用户下载
   Excel上传 → 解析导入 → 更新work_records
   选中记录 → 批量提交 → 外部系统
   ```

2. **第二步**：运行测试
   ```bash
   cd backend
   python test_api.py  # 测试所有API接口
   python check_db.py  # 验证数据库结构
   ```

3. **第三步**：修改前先备份
   ```bash
   cp backend/app.py backend/app.py.bak
   cp frontend/src/App.vue frontend/src/App.vue.bak
   ```

4. **第四步**：查看日志调试
   ```bash
   tail -f backend/logs/app.log
   tail -f backend/logs/error.log
   ```

---

## ✅ 项目检查清单

**启动前确认**：
- [ ] MySQL服务运行中
- [ ] 数据库 chronos 存在
- [ ] Python环境已激活（conda activate tornado）
- [ ] 所有依赖已安装（pip install -r requirements.txt）

**功能测试**：
- [ ] 配置管理：curl命令自动解析
- [ ] 生成记录：日期范围选择，调用外部API
- [ ] 记录列表：正确显示所有字段
- [ ] 编辑记录：修改后能保存
- [ ] Excel导出：下载的xlsx格式正确
- [ ] Excel导入：上传后数据更新
- [ ] 批量提交：能提交到外部系统
- [ ] 统计显示：人天、人月计算正确
- [ ] 多用户：不同username数据隔离

**性能检查**：
- [ ] 单次生成记录<5秒（30天范围）
- [ ] 日志文件自动轮询
- [ ] 数据库连接池正常

---

## 🔗 相关链接

- **Tornado文档**：https://www.tornadoweb.org/
- **SQLAlchemy异步文档**：https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Element Plus**：https://element-plus.org/
- **Vue 3**：https://vuejs.org/

---

**最后更新**：2025-12-31  
**维护者**：AI Assistant  
**版本**：2.0.0
