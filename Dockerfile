FROM selenium/standalone-edge:latest

# 切到 root 方便 apt 装包
USER root

# 安装 Python 和 pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip git fonts-noto-cjk locales && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    pip install --upgrade pip && \
    locale-gen zh_CN.UTF-8 && \
    update-locale LANG=zh_CN.UTF-8

# 克隆项目
WORKDIR /app
RUN git clone -b docker-compatibility-dev https://github.com/Patrick16262/March7thAssistantClone.git /app
RUN pip install -r requirements.txt

# 给启动脚本执行权限
RUN chmod +x /app/run.sh

# 启动 standalone + 执行测试
CMD ["/bin/bash", "/app/run.sh"]

# 启动命令
# docker run -d -p 4444:4444 -p 7900:7900 \
#   --shm-size="1g" \
#   --name "March7th Assistants" \
#   -v /app/config.yaml:{Your Home Path}/.m7a/config.yaml \
#   -v /app/cookies.json:{Your Home Path}/.m7a/cookies.json \
#   {image-name}:latest