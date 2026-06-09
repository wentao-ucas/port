# -*- coding: utf-8 -*-
"""检查数据库表结构"""
import os
import pymysql

# 连接配置（密码走环境变量，不硬编码）
config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'charset': 'utf8mb4'
}

try:
    # 连接MySQL
    conn = pymysql.connect(**config)
    cursor = conn.cursor()
    
    # 检查数据库
    cursor.execute("SHOW DATABASES LIKE 'chronos'")
    db_exists = cursor.fetchone()
    
    if db_exists:
        print("数据库 chronos 存在")
        
        # 切换到数据库
        cursor.execute("USE chronos")
        
        # 查看所有表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        if tables:
            print(f"\n找到 {len(tables)} 个表：")
            for table in tables:
                print(f"  - {table[0]}")
                
                # 显示表结构
                cursor.execute(f"DESCRIBE {table[0]}")
                columns = cursor.fetchall()
                print(f"    字段：")
                for col in columns:
                    print(f"      {col[0]:20s} {col[1]:20s} {col[2]:5s}")
                print()
        else:
            print(" 数据库中没有表")
    else:
        print("数据库 chronos 不存在")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"连接失败: {e}")
