# 工时报工系统 - Work Time Reporting System

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Tornado](https://img.shields.io/badge/Tornado-6.3.3-green.svg)](https://www.tornadoweb.org/)
[![Vue](https://img.shields.io/badge/Vue-3.3.4-brightgreen.svg)](https://vuejs.org/)
[![MySQL](https://img.shields.io/badge/MySQL-5.x-orange.svg)](https://www.mysql.com/)

一个基于Vue3 + Tornado + MySQL的异步工时报工系统，支持自动识别curl命令、批量生成记录、Excel导入导出、多用户隔离等功能。

## ✨ 核心特性

- 🔐 **智能认证识别**：粘贴浏览器curl命令，自动提取Authorization和Cookie
- 📅 **日期范围生成**：选择任意日期范围，自动查询实际可报工时并生成记录
- 📊 **智能统计**：自动计算总工时、人天(÷8)、人月(÷21.75)
- 📁 **Excel批量操作**：支持导出编辑后再导入，批量修改工时
- 👥 **多用户支持**：按username隔离数据，互不干扰
- 📝 **完整日志**：所有操作记录到日志，保留30天自动清理
- 🚀 **异步架构**：基于Tornado + SQLAlchemy异步IO，高性能

## 🚀 快速开始

### 启动服务

```bash
# Linux/Mac
chmod +x bin/control.sh
./bin/control.sh start

# Windows
bin\control.bat start
```

访问：http://localhost:18760

### 查看状态和日志

```bash
# 查看状态
./bin/control.sh status

# 查看实时日志
./bin/control.sh logs

# 停止服务
./bin/control.sh stop
```

## 📚 完整文档

- **[Agent.md](Agent.md)** - 🔥 AI Agent快速理解文档（核心，必读！）
- **[FRONTEND_UPDATE.md](FRONTEND_UPDATE.md)** - 前端更新详细说明
- **[详细安装部署](#-安装部署)** - 见下方

## 🏗️ 技术栈

- **后端**：Python 3.9 + Tornado 6.3.3 + MySQL + SQLAlchemy 2.0
- **前端**：Vue 3 + Element Plus + Vite
- **数据库**：MySQL 5.x (chronos)

## 📦 安装部署

### 1. 数据库准备

```sql
CREATE DATABASE chronos CHARACTER SET utf8mb4;
USE chronos;

-- 用户配置表
CREATE TABLE user_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    authorization TEXT,
    cookie TEXT,
    curl_template TEXT,
    template_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 工时记录表
CREATE TABLE work_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    work_date DATE NOT NULL,
    normal_hours DECIMAL(5,2) DEFAULT 0.00,
    overtime_hours DECIMAL(5,2) DEFAULT 0.00,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_date (username, work_date),
    KEY idx_username (username)
);
```

### 2. 配置数据库连接

编辑 `backend/config.py`：
```python
DB_CONFIG = {
    'user': 'root',
    'password': '你的密码',
    'host': 'localhost',
    'database': 'chronos'
}
```

### 3. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 4. 启动服务

```bash
./bin/control.sh start  # Linux/Mac
bin\control.bat start   # Windows
```

## 📖 使用流程

### 步骤1：配置认证（一次性）

1. 在原报工系统完成一次报工
2. F12 → Network → 找到 `reportWorkingHours`
3. 右键 → Copy as cURL (bash)
4. 粘贴到"配置管理"页面 → 自动识别 → 保存

### 步骤2：生成记录

1. "生成记录"页面 → 选择日期范围
2. 点击"生成记录" → 自动查询API → 生成工作日记录

### 步骤3：编辑工时

**方式A：单条编辑**
- 记录列表 → 点击"编辑" → 修改 → 保存

**方式B：批量编辑**
- 导出Excel → 在Excel中修改 → 导入Excel

### 步骤4：提交报工

- 勾选记录 → "提交到服务器" → 完成

## 🔌 API接口

详见 [Agent.md - API接口文档](Agent.md#-后端api接口)

快速示例：
```bash
# 获取记录
curl http://localhost:18760/worktime-api/records?username=test

# 查询某区间可报工时
curl -X POST http://localhost:18760/worktime-api/query-worktime \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-30"}'
```

## 🧪 测试

```bash
cd backend

# 测试数据库
python check_db.py

# 测试API（需先启动服务）
python test_api.py
```

## 📁 项目结构

```
.
├── bin/
│   ├── control.sh         # 启动脚本(Linux/Mac)
│   └── control.bat        # 启动脚本(Windows)
├── backend/
│   ├── app.py            # 主应用
│   ├── config.py         # 配置
│   ├── models/           # 数据模型
│   ├── utils/            # 工具类（db, logger, excel）
│   └── logs/             # 日志目录
├── frontend/             # Vue3前端
├── Agent.md              # 🔥 核心文档
└── README.md             # 本文件
```

## 🐛 故障排查

| 问题 | 解决方案 |
|------|----------|
| 数据库连接失败 | 检查MySQL服务、用户密码 |
| Token过期(401) | 重新复制curl命令 |
| async_session_maker错误 | 已修复，确保使用最新代码 |
| 日志文件过大 | `./bin/control.sh cleanup` |

更多问题见 [Agent.md](Agent.md)

## 📝 日志

- **位置**: `backend/logs/`
- **文件**: `app.log`(全部) + `error.log`(错误)
- **轮询**: 每天午夜，保留30天

## 🤝 参与开发

**准备工作**：
1. 先阅读 [Agent.md](Agent.md) 理解架构
2. 备份文件再修改
3. 查看日志调试：`tail -f backend/logs/app.log`

**关键代码位置** 见 [Agent.md - 代码导航索引](Agent.md#-代码导航索引)

## 📄 许可证

MIT License

---

**版本**: 2.0.0  
**最后更新**: 2025-12-31  
**核心文档**: [Agent.md](Agent.md) 🔥
