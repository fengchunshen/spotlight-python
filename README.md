# SpotLight Python 执行平面

基于 FastAPI + LangGraph 的工作流执行平面服务，提供统一的工作流编排与模型调用接口。

## 架构说明

- **统一接口**: `POST /v1/run_workflow` 接收执行载荷并返回 SSE 事件流
- **模型网关**: 使用 OneAPI (OpenAI 兼容协议)，支持流式输出
- **工作流引擎**: 基于 LangGraph 实现可扩展的工作流系统，支持复杂业务编排
- **工具系统**: 支持原生工具(NATIVE)和 HTTP 插件(HTTP)，统一工具调用接口
- **流式输出**: 基于 Server-Sent Events (SSE) 实现实时事件流，支持精细化事件追踪

## 快速开始

### 1. 环境要求

- Python 3.10+
- pip 或 conda

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 环境变量配置（可选）

创建 `.env` 文件或设置环境变量：

```bash
# 日志配置
LOG_LEVEL=INFO                    # 日志级别: DEBUG, INFO, WARNING, ERROR
LOG_TRACE_ENABLED=true            # 是否启用详细 trace 信息

# SSE 配置
SSE_KEEPALIVE_INTERVAL=30         # SSE 保活间隔（秒）

# HTTP 工具配置
HTTP_TOOL_TIMEOUT=30              # HTTP 工具默认超时时间（秒）
```

### 4. 启动服务

```bash
# 开发模式（自动重载）
uvicorn engine.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn engine.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 查看服务信息和可用工作流
curl http://localhost:8000/
```

### 6. 测试请求

```bash
curl -X POST http://localhost:8000/v1/run_workflow \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d @test_payload.json
```

## API 接口

### POST /v1/run_workflow

执行工作流，返回 SSE 事件流。

**请求体**: 符合《通用执行载荷协议标准》的 JSON 载荷

**响应**: `text/event-stream` 格式的 SSE 事件流

**事件类型**:
- `tool_thinking`: 工具思考过程
- `tool_start`: 工具调用开始
- `tool_result`: 工具调用结果
- `message_chunk`: 消息流式输出片段
- `error`: 错误信息
- `done`: 工作流完成（包含 usage 和 finish_reason）

### GET /

获取服务信息和可用工作流列表。

### GET /health

健康检查接口。

## 目录结构

```
engine/
  ├─ main.py              # FastAPI 入口 & SSE 接口
  ├─ config.py            # 全局配置
  ├─ logging_utils.py     # 日志封装与脱敏工具
  ├─ schemas/
  │   └─ payload.py       # 通用执行载荷模型（Pydantic）
  ├─ models/
  │   └─ llm_factory.py   # LLM 工厂（OneAPI 兼容）
  ├─ tools/
  │   ├─ base.py          # 原生工具基类
  │   ├─ http_tool.py     # HTTP 插件执行器
  │   └─ loader.py        # 工具加载器
  ├─ workflows/
  │   ├─ registry.py      # 工作流注册表
  │   └─ agent_chat.py    # 对话工作流示例
  └─ sse/
      └─ emitter.py       # SSE 事件封装
```

## 执行载荷示例

```json
{
  "task_meta": {
    "workflow_id": "agent_chat",
    "trace_id": "trace-123456",
    "user_id": "user-001"
  },
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "你好，请介绍一下你自己"
      }
    ],
    "variables": {}
  },
  "runtime_config": {
    "model": {
      "model_name": "gpt-4",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxx",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "tools": [
      {
        "type": "HTTP",
        "name": "weather",
        "description": "查询天气信息",
        "parameter_schema": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "城市名称"
            }
          }
        },
        "execution_config": {
          "url": "https://api.weather.com/v1/query",
          "method": "GET"
        }
      }
    ],
    "vault": {
      "weather_api_key": "xxx"
    }
  }
}
```

## 扩展开发

### 新增工作流

1. 在 `workflows/` 目录创建新模块（如 `my_workflow.py`）
2. 实现工作流构建函数，返回 LangGraph StateGraph
3. 在 `workflows/registry.py` 中注册工作流

示例：

```python
# workflows/my_workflow.py
from langgraph.graph import StateGraph
from langchain_core.language_models import BaseChatModel

def build_my_workflow_graph(llm: BaseChatModel):
    graph = StateGraph(...)
    # 构建图逻辑
    return graph.compile()

# workflows/registry.py
from engine.workflows.my_workflow import build_my_workflow_graph

WORKFLOWS = {
    "my_workflow": build_my_workflow_graph,
    # ...
}
```

### 新增原生工具

1. 继承 `BaseNativeTool` 并实现 `execute` 方法
2. 在 `tools/loader.py` 中注册工具类

### 新增 HTTP 工具

无需代码修改，通过执行载荷的 `runtime_config.tools` 配置即可动态加载。

## 协议文档

详细协议文档位于 `docs/` 目录：

- [通用执行载荷协议标准.md](docs/通用执行载荷协议标准.md) - 执行载荷结构定义
- [SSE 流式透传与透明代理协议标准.md](docs/SSE%20流式透传与透明代理协议标准.md) - SSE 事件协议
- [内部工具范式协议.md](docs/内部工具范式协议.md) - 原生工具开发规范
- [外部通用插件协议.md](docs/外部通用插件协议.md) - HTTP 工具协议
- [统一模型网关协议标准.md](docs/统一模型网关协议标准.md) - 模型调用协议
- [平台功能分工.md](docs/平台功能分工.md) - 平台架构说明
- [平台工具规范化.md](docs/平台工具规范化.md) - 工具开发规范

## 开发规范

- **类型注解**: 所有函数参数和返回值必须添加类型注解
- **异步优先**: I/O 操作使用 `async/await`
- **错误处理**: 使用早期返回模式，错误信息需脱敏处理
- **日志安全**: 禁止在日志中输出敏感信息（API Key、用户消息等）
- **trace_id**: 贯穿全链路，支持问题排查和链路追踪

详细规范请参考项目根目录下的 `.cursor/rules/` 配置文件。

## 许可证

[待补充]
