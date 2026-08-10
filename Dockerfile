# syntax=docker/dockerfile:1
#
# 金蝶云星空 MCP Server 容器镜像
# 第三方开源项目，非金蝶官方出品。
#
# 构建：
#   docker build -t kingdee-mcp .
#   # 国内网络慢可换源：
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ -t kingdee-mcp .
#
# 运行（远程 HTTP 模式，容器场景推荐）：
#   docker run --rm -p 8000:8000 --env-file .env kingdee-mcp
#   端点：http://<宿主机IP>:8000/mcp
#
# 运行（stdio 模式，给本地 MCP 客户端当子进程用）：
#   docker run -i --rm --env-file .env -e KINGDEE_MCP_TRANSPORT=stdio kingdee-mcp
#
# 自检配置是否正确（不起服务，跑一次金蝶登录）：
#   docker run --rm --env-file .env kingdee-mcp --check

FROM python:3.12-slim

# unixodbc：pyodbc 的运行期依赖，SQL Server 探查类工具会用到。
# 源码里 pyodbc 是懒加载（用到才 import），不装也能跑金蝶 API 那部分；
# 这里装上是为了避免"平时好好的、点到那几个工具才报错"。
RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 默认走官方源，保证任何地区都能构建；国内构建用 --build-arg 换镜像源。
ARG PIP_INDEX_URL=https://pypi.org/simple

# 只拷贝打包必需的文件，改代码时不会让依赖层缓存失效
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --index-url "${PIP_INDEX_URL}" .

# 不用 root 跑服务
RUN useradd --create-home --uid 10001 mcp
USER mcp

# 容器内必须监听 0.0.0.0：默认的 127.0.0.1 只在容器内部可达，宿主机连不进来，
# 这是容器化最常见的"端口映射了却连不上"的原因。
ENV KINGDEE_MCP_TRANSPORT=streamable-http \
    KINGDEE_MCP_HOST=0.0.0.0 \
    KINGDEE_MCP_PORT=8000

EXPOSE 8000

ENTRYPOINT ["kingdee-mcp"]
