# AppFlowyMCP — streamable HTTP MCP server for the self-hosted AppFlowy Cloud.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package and its deps. pycrdt ships manylinux wheels, no build tools needed.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .[collab]

# The MCP server itself does no auth — oauth-agents in front owns client-facing auth.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8000),4); s.close()" || exit 1

CMD ["python3", "-m", "appflowy_mcp.server"]