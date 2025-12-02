# API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **协议版本**: v1
- **内容类型**: `application/json`
- **响应类型**: `text/event-stream` (SSE)

## 接口列表

### 1. 健康检查

检查服务是否正常运行。

**请求:**
```
GET /health
```

**响应:**
```json
{
  "status": "healthy"
}
```

---

### 2. 服务信息

获取服务信息和可用工作流列表。

**请求:**
```
GET /
```

**响应:**
```json
{
  "service": "SpotLight Python Engine",
  "version": "0.1.0",
  "workflows": ["agent_chat"]
}
```

---

### 3. 执行工作流 (核心接口)

执行指定的 LangGraph 工作流并返回 SSE 事件流。

**请求:**
```
POST /v1/run_workflow
Content-Type: application/json
Accept: text/event-stream
```

**请求体 (Payload):**

```json
{
  "task_meta": {
    "workflow_id": "agent_chat",
    "trace_id": "trace-001",
    "user_id": "user-123"
  },
  "input": {
    "messages": [
      {
        "role": "system",
        "content": "你是一个有帮助的 AI 助手。"
      },
      {
        "role": "user",
        "content": "你好，请介绍一下你自己。"
      }
    ],
    "variables": {}
  },
  "runtime_config": {
    "model": {
      "provider": "openai",
      "model_name": "gpt-3.5-turbo",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxxxx",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "tools": [],
    "vault": {}
  }
}
```

**请求参数详解:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_meta | Object | 是 | 任务元数据 |
| task_meta.workflow_id | String | 是 | 工作流 ID（如 "agent_chat"） |
| task_meta.trace_id | String | 是 | 链路追踪 ID |
| task_meta.user_id | String | 是 | 用户 ID |
| input | Object | 是 | 输入上下文 |
| input.messages | Array | 是 | 消息列表 |
| input.messages[].role | String | 是 | 消息角色: system/user/assistant/tool |
| input.messages[].content | Any | 是 | 消息内容 |
| input.variables | Object | 否 | 变量字典 |
| runtime_config | Object | 是 | 运行时配置 |
| runtime_config.model | Object | 是 | 模型配置 |
| runtime_config.model.provider | String | 是 | 模型提供商 |
| runtime_config.model.model_name | String | 是 | 模型名称 |
| runtime_config.model.base_url | String | 是 | API 基础 URL |
| runtime_config.model.api_key | String | 是 | API 密钥 |
| runtime_config.model.temperature | Float | 否 | 温度参数，默认 0.7 |
| runtime_config.model.max_tokens | Integer | 否 | 最大 token 数 |
| runtime_config.tools | Array | 否 | 工具配置列表 |
| runtime_config.vault | Object | 否 | 密钥保险库 |

**响应 (SSE 事件流):**

#### 事件类型

##### 1. tool_thinking
思考/进度事件

```
id: uuid-1
event: tool_thinking
data: {"msg": "正在初始化工作流...", "trace_id": "trace-001"}
```

##### 2. tool_start
工具开始执行

```
id: uuid-2
event: tool_start
data: {"tool_name": "get_weather", "args": {"city": "北京"}, "trace_id": "trace-001"}
```

##### 3. tool_result
工具执行结果

```
id: uuid-3
event: tool_result
data: {"tool_name": "get_weather", "result": {"temp": 20, "weather": "晴"}, "trace_id": "trace-001"}
```

##### 4. message_chunk
消息片段（流式输出）

```
id: uuid-4
event: message_chunk
data: {"content": "你好！我是一个 AI 助手...", "trace_id": "trace-001"}
```

##### 5. done
执行完成

```
id: uuid-5
event: done
data: {"usage": 125, "finish_reason": "stop", "trace_id": "trace-001"}
```

finish_reason 可能的值:
- `stop`: 正常结束
- `length`: 达到最大长度
- `tool_calls`: 需要工具调用

##### 6. error
执行错误

```
id: uuid-6
event: error
data: {"code": 500, "msg": "工作流执行失败", "trace_id": "trace-001"}
```

常见错误码:
- `400`: 参数错误（如未知的 workflow_id）
- `500`: 服务器内部错误

##### 7. ping / keep-alive
保活事件

```
id: uuid-7
event: ping
data: {"msg": "keep-alive"}
```

或简单的注释:
```
: keep-alive
```

---

## 完整示例

### 示例 1: 简单对话

**请求:**
```bash
curl -N -X POST http://localhost:8000/v1/run_workflow \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "task_meta": {
      "workflow_id": "agent_chat",
      "trace_id": "test-001",
      "user_id": "user-001"
    },
    "input": {
      "messages": [
        {"role": "user", "content": "1+1等于几？"}
      ]
    },
    "runtime_config": {
      "model": {
        "provider": "openai",
        "model_name": "gpt-3.5-turbo",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-xxxxx"
      },
      "tools": [],
      "vault": {}
    }
  }'
```

**响应:**
```
id: abc-123
event: tool_thinking
data: {"msg": "正在初始化工作流...", "trace_id": "test-001"}

id: abc-124
event: tool_thinking
data: {"msg": "正在连接模型服务...", "trace_id": "test-001"}

id: abc-125
event: tool_thinking
data: {"msg": "正在执行工作流...", "trace_id": "test-001"}

id: abc-126
event: message_chunk
data: {"content": "1+1等于2。", "trace_id": "test-001"}

id: abc-127
event: done
data: {"usage": 0, "finish_reason": "stop", "trace_id": "test-001"}
```

### 示例 2: 使用 HTTP 工具

**请求:**
```json
{
  "task_meta": {
    "workflow_id": "agent_chat",
    "trace_id": "test-002",
    "user_id": "user-001"
  },
  "input": {
    "messages": [
      {"role": "user", "content": "查询北京的天气"}
    ]
  },
  "runtime_config": {
    "model": {
      "provider": "openai",
      "model_name": "gpt-3.5-turbo",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxxxx"
    },
    "tools": [
      {
        "type": "HTTP",
        "name": "get_weather",
        "description": "获取城市天气",
        "parameter_schema": {
          "type": "object",
          "properties": {
            "city": {"type": "string"}
          }
        },
        "execution_config": {
          "url": "https://api.weather.com/v1/current",
          "method": "GET",
          "auth_config": {
            "source": "weather_key",
            "target": "X-API-Key"
          }
        }
      }
    ],
    "vault": {
      "weather_key": "your-weather-api-key"
    }
  }
}
```

## 错误处理

### 参数验证错误

**请求缺少必填字段:**
```json
{
  "detail": [
    {
      "loc": ["body", "task_meta", "workflow_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 业务错误

**未知的 workflow_id:**
```
id: xxx
event: error
data: {"code": 400, "msg": "Unknown workflow_id: unknown_workflow", "trace_id": "test-001"}
```

**工作流执行失败:**
```
id: xxx
event: error
data: {"code": 500, "msg": "工作流执行失败", "trace_id": "test-001"}
```

## 客户端示例

### Python

```python
import httpx
import json

async def call_workflow(payload: dict):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/v1/run_workflow",
            json=payload,
            headers={"Accept": "text/event-stream"},
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    event_type = line.split("\n")[1].split(": ")[1]
                    print(f"[{event_type}] {data}")
```

### JavaScript

```javascript
const payload = { /* ... */ };

const response = await fetch('http://localhost:8000/v1/run_workflow', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream'
  },
  body: JSON.stringify(payload)
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value);
  const lines = text.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.substring(6));
      console.log(data);
    }
  }
}
```

### Java

```java
OkHttpClient client = new OkHttpClient();

Request request = new Request.Builder()
    .url("http://localhost:8000/v1/run_workflow")
    .post(RequestBody.create(payloadJson, MediaType.parse("application/json")))
    .addHeader("Accept", "text/event-stream")
    .build();

try (Response response = client.newCall(request).execute()) {
    BufferedReader reader = new BufferedReader(
        new InputStreamReader(response.body().byteStream())
    );
    
    String line;
    while ((line = reader.readLine()) != null) {
        if (line.startsWith("data: ")) {
            String json = line.substring(6);
            // 解析 JSON
        }
    }
}
```

## 性能考虑

- **超时时间**: 建议设置 60-120 秒超时
- **保活机制**: 服务端每 30 秒发送一次 keep-alive
- **并发限制**: 建议单机不超过 100 并发请求
- **流式处理**: 客户端应逐行处理 SSE 事件，不要等待全部完成

## 安全建议

1. 不在日志中记录 `api_key` 和 `vault` 内容
2. 使用 HTTPS 传输敏感数据
3. 对 API 密钥进行定期轮换
4. 实施请求频率限制和认证机制

