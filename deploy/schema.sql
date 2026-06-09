-- 工时报工系统 建库建表脚本
-- 用法： mysql -u root -p < schema.sql
-- 注：后端首次启动也会自动建表，这份脚本用于手动初始化 / 留档 / 核对结构。

CREATE DATABASE IF NOT EXISTS chronos
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE chronos;

-- 用户认证配置（按 username = token里的 user_id 隔离，一人一行）
CREATE TABLE IF NOT EXISTS user_configs (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(100) NOT NULL COMMENT '用户名(=token的user_id)',
  `authorization` TEXT        COMMENT 'Authorization token',
  cookie        VARCHAR(500)  COMMENT 'Cookie',
  curl_template TEXT          COMMENT '完整的curl命令',
  template_data TEXT          COMMENT '提交模板数据JSON',
  created_at    DATETIME      DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户认证配置';

-- 工时记录
CREATE TABLE IF NOT EXISTS work_records (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  username       VARCHAR(100) NOT NULL COMMENT '用户名(=token的user_id)',
  work_date      DATE         NOT NULL COMMENT '工作日期',
  normal_hours   FLOAT        DEFAULT 0 COMMENT '正常工时',
  overtime_hours FLOAT        DEFAULT 0 COMMENT '加班工时',
  avail_normal   FLOAT        NULL COMMENT '可填正常工时上限',
  avail_overtime FLOAT        NULL COMMENT '可填加班工时上限',
  work_content   TEXT         NULL COMMENT '工作内容',
  status         VARCHAR(20)  DEFAULT 'pending' COMMENT '状态: pending/submitted/failed',
  created_at     DATETIME     DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_date (username, work_date),
  KEY idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工时记录';
