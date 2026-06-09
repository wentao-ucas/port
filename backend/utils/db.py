# -*- coding: utf-8 -*-
"""数据库连接和会话管理"""

import aiomysql
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import DATABASE_URL, DB_CONFIG

# SQLAlchemy Base
Base = declarative_base()

# 异步引擎和会话工厂（全局变量）
engine = None
async_session_maker = None


def get_session_maker():
    """获取会话工厂"""
    global async_session_maker
    if async_session_maker is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return async_session_maker


async def init_db():
    """初始化数据库连接"""
    global engine, async_session_maker
    
    # 创建异步引擎
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
    )
    
    # 创建会话工厂
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # 创建数据库（如果不存在）
    await create_database_if_not_exists()
    
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 确保新增列存在
    await ensure_work_content_column()
    await ensure_avail_columns()
    await ensure_display_name_column()
    await ensure_workrecord_task_columns()

    print(f"数据库初始化完成，async_session_maker 类型: {type(async_session_maker)}")


async def create_database_if_not_exists():
    """创建数据库（如果不存在）"""
    try:
        # 连接到MySQL服务器（不指定数据库）
        conn = await aiomysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            charset=DB_CONFIG['charset']
        )
        
        async with conn.cursor() as cursor:
            # 创建数据库
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} "
                f"CHARACTER SET {DB_CONFIG['charset']} COLLATE utf8mb4_unicode_ci"
            )
            print(f"数据库 {DB_CONFIG['database']} 已就绪")
        
        conn.close()
    except Exception as e:
        print(f"创建数据库失败: {e}")
        raise


async def ensure_work_content_column():
    """确保 work_records 表存在 work_content 列（用于存储工作内容）"""
    try:
        conn = await aiomysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            db=DB_CONFIG['database'],
            charset=DB_CONFIG['charset']
        )

        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME='work_records' AND COLUMN_NAME='work_content'
                """,
                (DB_CONFIG['database'],)
            )
            exists = (await cursor.fetchone())[0]

            if not exists:
                await cursor.execute(
                    "ALTER TABLE work_records ADD COLUMN work_content TEXT COMMENT '工作内容'"
                )
                print("已为 work_records 增加 work_content 列")

        conn.close()
    except Exception as e:
        print(f"检查/新增 work_content 列失败: {e}")
        raise


async def ensure_avail_columns():
    """确保 work_records 表存在 avail_normal / avail_overtime 列（可填工时上限）"""
    try:
        conn = await aiomysql.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            db=DB_CONFIG['database'],
            charset=DB_CONFIG['charset']
        )

        async with conn.cursor() as cursor:
            for col in ('avail_normal', 'avail_overtime'):
                await cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=%s AND TABLE_NAME='work_records' AND COLUMN_NAME=%s
                    """,
                    (DB_CONFIG['database'], col)
                )
                exists = (await cursor.fetchone())[0]
                if not exists:
                    await cursor.execute(
                        f"ALTER TABLE work_records ADD COLUMN {col} FLOAT NULL COMMENT '可填工时上限'"
                    )
                    print(f"已为 work_records 增加 {col} 列")

        conn.close()
    except Exception as e:
        print(f"检查/新增 avail 列失败: {e}")
        raise


def _user_name_from_jwt(authorization):
    """从 Authorization(JWT) 解析 user_name（只解 payload，不验签）。失败返回 None。"""
    if not authorization:
        return None
    import base64
    import json as _json
    t = authorization.strip()
    if t.lower().startswith('bearer '):
        t = t[7:].strip()
    try:
        parts = t.split('.')
        if len(parts) < 2:
            return None
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        data = _json.loads(base64.urlsafe_b64decode(payload))
        n = str(data.get('user_name') or '').strip()
        return n or None
    except Exception:
        return None


async def ensure_display_name_column():
    """确保 user_configs 有 display_name 列(显示名/英文名)，并回填已有行(从 authorization 解析)。"""
    try:
        conn = await aiomysql.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'], user=DB_CONFIG['user'],
            password=DB_CONFIG['password'], db=DB_CONFIG['database'], charset=DB_CONFIG['charset']
        )
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME='user_configs' AND COLUMN_NAME='display_name'
                """,
                (DB_CONFIG['database'],)
            )
            exists = (await cursor.fetchone())[0]
            if not exists:
                await cursor.execute(
                    "ALTER TABLE user_configs ADD COLUMN display_name VARCHAR(100) NULL COMMENT '显示名(user_name)'"
                )
                print("已为 user_configs 增加 display_name 列")
            # 回填：display_name 为空的行，从 authorization 里解析 user_name
            await cursor.execute(
                "SELECT username, authorization FROM user_configs WHERE display_name IS NULL OR display_name=''"
            )
            rows = await cursor.fetchall()
            filled = 0
            for username, auth in rows:
                name = _user_name_from_jwt(auth)
                if name:
                    await cursor.execute(
                        "UPDATE user_configs SET display_name=%s WHERE username=%s", (name, username)
                    )
                    filled += 1
            await conn.commit()
            if filled:
                print(f"已回填 {filled} 行 display_name")
        conn.close()
    except Exception as e:
        print(f"检查/新增 display_name 列失败: {e}")
        raise


async def ensure_workrecord_task_columns():
    """确保 work_records 有任务快照列 task_id/task_name/plan_start/plan_end。
    旧记录这些列为 NULL（不回填——无法可靠还原历史记录当初属于哪个任务）。"""
    cols = {
        'task_id': "ALTER TABLE work_records ADD COLUMN task_id VARCHAR(50) NULL COMMENT '报工任务id快照'",
        'task_name': "ALTER TABLE work_records ADD COLUMN task_name VARCHAR(200) NULL COMMENT '报工任务名快照'",
        'plan_start': "ALTER TABLE work_records ADD COLUMN plan_start VARCHAR(20) NULL COMMENT '任务计划开始快照'",
        'plan_end': "ALTER TABLE work_records ADD COLUMN plan_end VARCHAR(20) NULL COMMENT '任务计划结束快照'",
    }
    try:
        conn = await aiomysql.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'], user=DB_CONFIG['user'],
            password=DB_CONFIG['password'], db=DB_CONFIG['database'], charset=DB_CONFIG['charset']
        )
        async with conn.cursor() as cursor:
            for col, ddl in cols.items():
                await cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=%s AND TABLE_NAME='work_records' AND COLUMN_NAME=%s
                    """,
                    (DB_CONFIG['database'], col)
                )
                if not (await cursor.fetchone())[0]:
                    await cursor.execute(ddl)
                    print(f"已为 work_records 增加 {col} 列")
        conn.close()
    except Exception as e:
        print(f"检查/新增 work_records 任务快照列失败: {e}")
        raise


async def get_session() -> AsyncSession:
    """获取数据库会话"""
    async with async_session_maker() as session:
        yield session


async def close_db():
    """关闭数据库连接"""
    global engine
    if engine:
        await engine.dispose()
        print("数据库连接已关闭")
