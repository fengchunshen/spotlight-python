# SpotLight Python 执行平面

基于 FastAPI + LangGraph 的工作流执行平面服务，提供统一的工作流编排与模型调用接口。

## 架构说明

- **统一接口**: `POST /v1/run_workflow` 接收执行载荷并返回 SSE 事件流
- **模型网关**: 使用 OneAPI (OpenAI 兼容协议)
- **工作流引擎**: 基于 LangGraph 实现可扩展的工作流系统
- **工具系统**: 支持原生工具(NATIVE)和 HTTP 插件(HTTP)

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
uvicorn engine.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 测试请求

```bash
curl -X POST http://localhost:8000/v1/run_workflow \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d @test_payload.json
```

## 目录结构

```
engine/
  ├─ main.py              # FastAPI 入口 & SSE 接口
  ├─ config.py            # 全局配置
  ├─ logging_utils.py     # 日志封装
  ├─ schemas/
  │   └─ payload.py       # 通用执行载荷模型
  ├─ models/
  │   └─ llm_factory.py   # LLM 工厂
  ├─ tools/
  │   ├─ base.py          # 原生工具基类
  │   ├─ http_tool.py     # HTTP 插件执行器
  │   └─ loader.py        # 工具加载器
  ├─ workflows/
  │   ├─ registry.py      # 工作流注册表
  │   └─ agent_chat.py    # 对话工作流
  └─ sse/
      └─ emitter.py       # SSE 事件封装
```

## 扩展开发

- 新增工作流: 在 `workflows/` 目录添加模块并注册到 `registry.py`
- 新增原生工具: 继承 `BaseNativeTool` 并在 `loader.py` 中注册
- 新增 HTTP 工具: 通过执行载荷的 `runtime_config.tools` 配置即可

## 协议文档

- 通用执行载荷协议标准.md
- SSE 流式透传与透明代理协议标准.md
- 内部工具范式协议.md
- 外部通用插件协议.md

