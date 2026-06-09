# 工时报工系统 - 升级说明

## 已完成的升级

### 1. 数据库迁移
- ✅ 从SQLite迁移到MySQL
- ✅ 数据库名：`chronos`
- ✅ 使用SQLAlchemy ORM + aiomysql异步连接
- ✅ 自动创建数据库和表结构

### 2. 多用户支持
- ✅ 每个用户有独立的配置（Authorization、Cookie）
- ✅ 每个用户的工时记录相互隔离
- ✅ 通过username参数区分用户

### 3. 项目结构规范化
```
backend/
  ├── app.py              # 主应用
  ├── config.py           # 配置文件（MySQL连接信息）
  ├── models/
  │   ├── user_config.py  # 用户配置模型
  │   └── work_record.py  # 工时记录模型
  ├── utils/
  │   ├── db.py           # 数据库连接管理
  │   └── excel_helper.py # Excel导入导出
  └── requirements.txt
```

### 4. 新增功能
- ✅ 日期范围生成：输入开始和结束日期，从API读取实际可报工时
- ✅ Excel导出：导出所有记录到Excel文件
- ✅ Excel导入：从Excel批量更新工时数据
- ✅ 编辑功能：单条记录编辑
- ✅ 统计功能：自动计算人天、人月

## 前端待更新功能

需要修改 `frontend/src/App.vue`：

1. **生成记录页改造**：
   - 改为日期范围选择（开始日期 → 结束日期）
   - 删除"正常工时"和"加班工时"输入框（从API读取）
   - 说明：系统自动从API查询每天的实际可报工时

2. **报工管理页增强**：
   - 添加"导出Excel"按钮
   - 添加"导入Excel"按钮
   - 导出后可在Excel中批量修改，然后导入回系统

3. **用户名支持**（可选）：
   - 添加用户名输入框（或自动从系统获取）
   - 当前默认用户名：`default_user`

## API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/worktime-api/config` | GET/POST | 获取/保存配置 |
| `/worktime-api/query-worktime` | POST | 查询某区间可报工时 |
| `/worktime-api/fill-draft` | POST | 日历点选→生成待填报 |
| `/worktime-api/records` | GET/PUT/DELETE | 获取/更新/删除记录 |
| `/worktime-api/excel/export` | GET | 导出Excel |
| `/worktime-api/excel/import` | POST | 导入Excel |
| `/worktime-api/submit` | POST | 批量提交报工 |

## 快速测试

1. **启动服务器**：
   ```bash
   conda activate tornado
   cd D:\code\port\backend
   python app.py
   ```

2. **测试API**（PowerShell）：
   ```powershell
   # 测试配置保存
   $body = @{
       curl_template = "你的curl命令"
   } | ConvertTo-Json
   
   Invoke-RestMethod -Uri "http://localhost:18760/worktime-api/config?username=demo_user" `
       -Method POST -Body $body -ContentType "application/json"
   
   # 查询某区间可报工时
   $body = @{
       start_date = "2026-06-01"
       end_date = "2026-06-30"
   } | ConvertTo-Json
   
   Invoke-RestMethod -Uri "http://localhost:18760/worktime-api/query-worktime" `
       -Method POST -Body $body -ContentType "application/json"
   
   # 导出Excel
   Invoke-WebRequest -Uri "http://localhost:18760/worktime-api/excel/export?username=demo_user" `
       -OutFile "worktime.xlsx"
   ```

## 数据库表结构

### user_configs表
```sql
CREATE TABLE user_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) UNIQUE NOT NULL COMMENT '用户名',
    authorization TEXT COMMENT 'Authorization token',
    cookie VARCHAR(500) COMMENT 'Cookie',
    curl_template TEXT COMMENT '完整的curl命令',
    template_data TEXT COMMENT '请求模板数据JSON',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### work_records表
```sql
CREATE TABLE work_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL COMMENT '用户名',
    work_date DATE NOT NULL COMMENT '工作日期',
    normal_hours FLOAT DEFAULT 0.0 COMMENT '正常工时',
    overtime_hours FLOAT DEFAULT 0.0 COMMENT '加班工时',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_user_date (username, work_date)
);
```

## 注意事项

1. **认证信息隔离**：每个用户的Authorization和Cookie独立存储，不会互相干扰
2. **工时来源**：生成记录时从`getInitMsg` API读取实际可报工时，而不是手动输入
3. **Excel格式**：导出的Excel包含ID、日期、星期、工时等列，修改后导入会根据ID更新
4. **批量编辑**：推荐使用Excel进行批量修改，更高效

## 下一步

需要更新前端Vue代码以匹配新的API接口。主要修改：
- 生成记录表单改为日期范围选择
- 添加Excel导入导出按钮
- 测试完整流程
