#!/bin/bash
# 启动 Selenium Standalone（后台跑）
/opt/bin/entry_point.sh &

# 等待浏览器服务就绪
echo "Waiting Selenium Grid to start..."
sleep 5

# 执行你的自动化测试
echo "Start March7th Assistants ..."
python tests/test_main.py