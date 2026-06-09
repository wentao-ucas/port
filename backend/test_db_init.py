# 测试数据库初始化
import asyncio
from utils import db

async def test():
    print("开始初始化数据库...")
    await db.init_db()
    print(f"async_session_maker 类型: {type(db.async_session_maker)}")
    print(f"async_session_maker 是否可调用: {callable(db.async_session_maker)}")
    
    if db.async_session_maker:
        print("async_session_maker 已成功创建")
        async with db.async_session_maker() as session:
            print("成功创建session")
    else:
        print("async_session_maker 为 None")

asyncio.run(test())
