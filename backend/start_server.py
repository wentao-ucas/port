import subprocess
import sys

# 启动服务器
subprocess.Popen([sys.executable, 'app.py'], cwd=r'D:\code\port\backend')
print("服务器已在后台启动")
