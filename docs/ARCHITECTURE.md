# 架构说明

## 整体架构

SpotLight Python 执行平面采用 **FastAPI + LangGraph** 架构，实现统一的工作流执行接口。

```
┌─────────────────┐
│  Java 控制平面  │
│  (调度/编排)    │
└────────┬────────┘
         │ HTTP/SSE
         ▼
┌─────────────────────────────────┐
│   FastAPI 执行平面              │
│                                 │
│  POST /v1/run_workflow          │
│    │                            │
│    ├─> Payload 解析             │
│    ├─> LLM 工厂                │
│    ├─> 工具加载器               │
│    └─> LangGraph 工作流         │
│         │                       │
│         ├─> agent_chat          │
│         ├─> [更多工作流...]     │
│         │                       │
│         └─> SSE 事件流输出      │
└─────────────────────────────────┘
         │
         ├─> OneAPI (模型网关)
         └─> HTTP 插件 / 原生工具
```

## 核心模块

### 1. 执行载荷（schemas/payload.py）

定义符合《通用执行载荷协议标准》的 Pydantic 模型：
- `TaskMeta`: 任务元数据（workflow_id, trace_id, user_id）
- `InputContext`: 输入上下文（messages, variables）
- `RuntimeConfig`: 运行时配置（model, tools, vault）

### 2. 模型工厂（models/llm_factory.py）

基于 `ModelConfig` 构造 `ChatOpenAI` 客户端：
- 支持 OneAPI（OpenAI 兼容协议）
- 默认开启 streaming 模式
- 可配置 temperature、max_tokens 等参数

### 3. 工具系统（tools/）

#### 3.1 原生工具（base.py）
- 抽象基类 `BaseNativeTool`
- 定义统一的 `run` 接口和 `args_schema`
- 支持通过反射加载自定义工具

#### 3.2 HTTP 工具（http_tool.py）
- 通用 HTTP 插件执行器
- 支持从 vault 注入认证信息
- 支持 GET/POST/PUT/DELETE 方法

#### 3.3 工具加载器（loader.py）
- 从 `runtime_config.tools` 动态加载工具
- 为每个工具创建独立的闭包
- 统一工具调用接口

### 4. LangGraph 工作流（workflows/）

#### 4.1 工作流注册表（registry.py）
- 维护 `workflow_id -> 构图函数` 映射
- 统一工作流加载接口
- 支持列出所有可用工作流

#### 4.2 对话工作流（agent_chat.py）
- 基础对话型工作流实现
- 支持 system/user/assistant 消息
- 已为后续支持工具调用预留扩展点

### 5. SSE 事件封装（sse/emitter.py）

符合《SSE 流式透传协议》的事件格式化工具：
- `format_sse`: 通用 SSE 事件格式化
- `format_tool_thinking`: 工具思考事件
- `format_tool_start`: 工具开始执行
- `format_tool_result`: 工具执行结果
- `format_message_chunk`: 消息片段
- `format_done`: 完成事件
- `format_error`: 错误事件

### 6. FastAPI 入口（main.py）

提供单一业务接口：
- `POST /v1/run_workflow`: 执行工作流
- 接收 Payload，返回 SSE 事件流
- 统一异常处理与日志记录

## 数据流

1. **请求接收**: Java 控制平面发送 Payload 到 `/v1/run_workflow`
2. **参数解析**: Pydantic 自动验证和解析 Payload
3. **资源准备**: 
   - 构建 LLM 客户端
   - 加载工具集
   - 获取工作流构建器
4. **工作流执行**: 
   - 创建初始状态
   - 调用 LangGraph 图执行
   - 逐步输出 SSE 事件
5. **结果返回**: 
   - 输出 message_chunk 事件
   - 输出 done 事件（含 usage 和 finish_reason）
   - 或输出 error 事件（发生异常时）

## 扩展点

### 新增工作流

1. 在 `workflows/` 目录创建新模块（如 `my_workflow.py`）
2. 实现构图函数 `build_my_workflow_graph(llm: BaseChatModel)`
3. 在 `registry.py` 中注册：`"my_workflow": build_my_workflow_graph`

### 新增原生工具

1. 创建工具类继承 `BaseNativeTool`
2. 定义 `name`, `description`, `args_schema`
3. 实现 `run` 方法
4. 在 `loader.py` 中通过反射加载

### 新增 HTTP 工具

无需修改代码，只需在 Payload 的 `runtime_config.tools` 中配置：
```json
{
  "type": "HTTP",
  "name": "tool_name",
  "description": "工具描述",
  "execution_config": {
    "url": "https://api.example.com/endpoint",
    "method": "POST",
    "auth_config": {
      "source": "api_key_name",
      "target": "X-API-Key"
    }
  }
}
```

## 安全考虑

1. **日志脱敏**: 不在日志中打印完整请求体、用户消息或 vault 内容
2. **错误过滤**: 返回给前端的错误消息不泄露内部实现细节
3. **密钥注入**: vault 中的密钥只在请求头中注入，不出现在日志或响应中
4. **trace_id 贯穿**: 全链路追踪，方便排查问题

## 性能优化

1. **异步 IO**: 使用 async/await 处理 HTTP 请求和工具调用
2. **流式输出**: SSE 逐步输出结果，不等待完整结果
3. **连接复用**: httpx.AsyncClient 自动管理连接池
4. **超时控制**: 为 HTTP 工具设置超时时间，避免长时间阻塞

## 后续规划

1. **流式执行**: 使用 LangGraph 的 `astream_events` API，精细化事件输出
2. **工具调用**: 在 agent_chat 中引入 function calling 和工具节点
3. **状态持久化**: 支持长时间运行的工作流状态保存与恢复
4. **观测性增强**: 接入分布式追踪系统（如 OpenTelemetry）
5. **性能监控**: 添加 Prometheus metrics 采集

