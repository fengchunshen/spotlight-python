### 知识库管理 REST 接口规范（管理面）

#### 目标与范围
- 覆盖知识库的创建、删除、文档入库/删除、配置更新、列举等管理操作。
- 不纳入内部工具范式，不写入 `sys_ai_plugin`；走独立 REST 路由。
- 保障租户/用户隔离、权限校验、日志脱敏；可选提供查询的流式返回，但默认一次性 JSON。

#### 路由前缀
- 建议：`/v1/knowledge`

#### 通用约定
- 请求与响应均使用 Pydantic v2 模型做校验（仅服务内使用，不镜像 `sys_ai_plugin`）。
- 所有请求需带 `trace_id`（推荐在 `task_meta.trace_id`）与用户/租户信息。
- 日志需脱敏，不记录全文内容或密钥；错误返回用户友好文案。
- 访问控制在路由或服务层做早返回校验。

#### 接口列表（示例草案）

1) `POST /v1/knowledge/create`
   - 参数：`kb_id?`（可由后端生成）、`kb_name`、`owner`、`tenant`、`visibility`、`description?`、`embedding_model`、`vector_store_config`
   - 返回：`kb_id`、配置概览、trace_id

2) `POST /v1/knowledge/delete`
   - 参数：`kb_id`、`owner`/`tenant`、`soft_delete?`
   - 返回：删除结果、trace_id

3) `POST /v1/knowledge/upsert`
   - 参数：`kb_id`、`docs`（列表，含 `doc_id?`、`content`、`metadata`）、`chunking_config`、`rerank_on_write?`
   - 返回：写入统计（成功/失败数、已存在覆盖数）、trace_id

4) `POST /v1/knowledge/delete_docs`
   - 参数：`kb_id`、`doc_ids` 或 `filters`
   - 返回：删除统计、trace_id

5) `POST /v1/knowledge/update_config`
   - 参数：`kb_id`、可变更项（`embedding_model`、`chunking`、`max_tokens`、`acl/visibility` 等）
   - 返回：新的配置摘要、trace_id

6) `POST /v1/knowledge/list`
   - 参数：`owner`/`tenant`、分页/过滤
   - 返回：知识库列表、trace_id

7) `POST /v1/knowledge/list_docs`
   - 参数：`kb_id`、分页/过滤
   - 返回：文档/分片列表摘要、trace_id

8) `POST /v1/knowledge/query`
   - 参数：`kb_id`、`query`、`top_k?`、`filters?`、`with_rerank?`、`return_sources?`、`stream?`
   - 返回：
     - `stream=false`：一次性 JSON，含 `answer`、`contexts`、`usage?`
     - `stream=true`：SSE，事件建议沿用 `tool_thinking/tool_start/tool_result/message_chunk/done/error`，使用 `sse/emitter.py.format_sse`

#### 目录与实现建议
- 路由文件：`engine/routers/knowledge.py`（示例），使用 FastAPI 路由。
- 服务层：`engine/services/knowledge_service.py`，封装向量库/存储逻辑；路由层只做校验与调度。
- 可复用 `import/knowledge` 中的切分、嵌入、向量写入模块，抽取为可调用函数。

#### 安全与日志
- 统一透传 `trace_id`，重要操作记录审计日志（脱敏）。
- 失败早返回，错误信息对用户友好；内部异常不暴露堆栈细节。
- 严禁在日志中输出全文、密钥或向量原文；必要时做摘要或截断。

#### 与推理面的衔接
- 推理面（对话/RAG）仍通过 `/v1/run_workflow` + 内部工具/工作流实现，单独文档描述（见 `docs/内部工具范式协议.md`）。
- 管理面与推理面共享的模型/配置需统一定义，避免重复配置或字段漂移。

