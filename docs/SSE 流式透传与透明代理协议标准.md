### **1. 核心定义**
本协议定义了控制平面（RuoYi）与执行平面（Python）之间，以及控制平面与前端（Frontend）之间的实时通信标准。

+ 流式透传：RuoYi 建立一条零缓冲管道，将 Python 产生的 SSE 数据包，以字节级（Byte-level）或事件级（Event-level）实时转发给前端，确保“首字延迟” (TTFT) 仅取决于 Python 推理速度，不受 Java GC 或缓冲策略影响。
+ 透明代理：RuoYi 在转发过程中扮演**中间人（Man-in-the-Middle）**角色。它对流内容进行非侵入式监听，用于执行计费扣除、日志记录和敏感词实时阻断，但对正常业务逻辑不可见。



### 2. 事件流协议标准
这是 Python 发送给 Java，Java 最终转发给前端的统一语言。采用标准SSE格式。

```json
id: <UUID>
event: <事件类型>
data: <JSON对象>
```

**示例：**

| **<font style="color:rgb(31, 31, 31);">事件类型 (event)</font>** | **<font style="color:rgb(31, 31, 31);">触发时机</font>** | **<font style="color:rgb(31, 31, 31);">data 载荷结构</font>** | **<font style="color:rgb(31, 31, 31);">前端交互逻辑</font>** |
| --- | --- | --- | --- |
| `<font style="color:rgb(68, 71, 70);">tool_thinking</font>` | <font style="color:rgb(31, 31, 31);">Python 开始规划</font> | `<font style="color:rgb(68, 71, 70);">{"msg": "正在分析用户意图..."}</font>` | <font style="color:rgb(31, 31, 31);">显示加载动画或思考状态</font> |
| `<font style="color:rgb(68, 71, 70);">tool_start</font>` | <font style="color:rgb(31, 31, 31);">决定调用某工具</font> | `<font style="color:rgb(68, 71, 70);">{"tool": "qcc", "input": "字节跳动"}</font>` | <font style="color:rgb(31, 31, 31);">渲染“正在调用企查查...”折叠面板</font> |
| `<font style="color:rgb(68, 71, 70);">tool_result</font>` | <font style="color:rgb(31, 31, 31);">工具执行完毕</font> | `<font style="color:rgb(68, 71, 70);">{"tool": "qcc", "status": "success", "result_preview": "..."}</font>` | <font style="color:rgb(31, 31, 31);">更新面板状态为</font><font style="color:rgb(31, 31, 31);">✅</font><font style="color:rgb(31, 31, 31);">，折叠详细结果</font> |
| `<font style="color:rgb(68, 71, 70);">message_chunk</font>` | <font style="color:rgb(31, 31, 31);">LLM 生成文本片段</font> | `<font style="color:rgb(68, 71, 70);">"注"</font>`<br/><font style="color:rgb(31, 31, 31);"> (纯字符串或 JSON)</font> | <font style="color:rgb(31, 31, 31);">触发打字机效果，追加到对话框</font> |
| `<font style="color:rgb(68, 71, 70);">error</font>` | <font style="color:rgb(31, 31, 31);">发生异常</font> | `<font style="color:rgb(68, 71, 70);">{"code": 500, "msg": "API Key 无效"}</font>` | <font style="color:rgb(31, 31, 31);">停止生成，弹出错误提示</font> |
| `<font style="color:rgb(68, 71, 70);">done</font>` | <font style="color:rgb(31, 31, 31);">流程彻底结束</font> | `<font style="color:rgb(68, 71, 70);">{"usage": 500, "finish_reason": "stop"}</font>` | <font style="color:rgb(31, 31, 31);">关闭连接，前端停止光标闪烁，显示Token消耗</font> |


****

### 3. RuoYi 网关实现机制 
RuoYi  采用 **Spring WebClient** 实现全链路异步非阻塞 I/O (NIO)  

#### 3.1 建立连接
1. **前端 -> RuoYi**：发起 `POST /api/chat/completions` (携带 `Accept: text/event-stream`)。
2. **RuoYi -> Python**：使用 `WebClient` (Spring WebFlux) 或 `OkHttp` (Async Mode) 发起内部长连接请求。
3. **管道对接**：RuoYi 获得 Python 的响应流 `Flux<DataBuffer>` 或 `InputStream`，立即封装为响应给前端的 `SseEmitter` 或 `ResponseBodyEmitter`。



#### 3.1 建立响应式管道
RuoYi 利用 Reactor 编程模型，建立从 Python 到前端的“背压（Backpressure）”感知管道。

1. **前端请求接入**：
    - Controller 层接收前端 `POST` 请求。
    - **关键变动**：返回类型不再是简单的 POJO，而是 `SseEmitter` (Servlet 栈) 或 `Flux<ServerSentEvent>` (WebFlux 栈)。鉴于 RuoYi 多为 Servlet 架构，推荐使用 `**SseEmitter**`** 结合 WebClient** 的桥接模式。
2. **Python 连接建立 (WebClient)**：
    - 使用 `WebClient` 发起对 Python Engine 的内部调用。

```java
WebClient client = WebClient.create("http://megumi-engine");
Flux<String> pythonStream = client.post()
.uri("/v1/run_workflow")
.bodyValue(payload)
.accept(MediaType.TEXT_EVENT_STREAM) // 声明接收 SSE 流
.retrieve()
.bodyToFlux(String.class); //以此建立流式通道，而非一次性读取
```

3. **管道对接与桥接**：
+ 将 `WebClient` 产生的 `Flux` 流，通过订阅的方式，逐个写入 `SseEmitter` 的 `OutputStream`。
+ 这一步实现了**零缓冲透传**：Python 吐出一个 chunk，Java 内存几乎不驻留，直接刷入网络卡缓冲区发给前端。

#### 3.2 旁路监听模型 (Side-Channel Observer via Reactor)
利用 WebClient 的响应式特性，通过 `**doOnNext**` 算子实现“T型监听”，**确保审计逻辑绝不阻塞业务流数据的转发**。

+ **实现机制**： 在 `Flux` 链上挂载钩子函数，对流经的数据进行监听

```java
pythonStream
    .doOnNext(rawJson -> {
        // --- 旁路监听区域 (Side-Channel) ---
        // 1. 快速解析: 判断 event 类型
        // 2. 异步分发: 如果是 'done'，丢给 RabbitMQ 或 线程池去扣费
        // 3. 安全阻断: 如果含敏感词，抛出异常打断流
        asyncAuditService.analyze(rawJson); 
    })
    .subscribe(
        data -> sseEmitter.send(data), // 正常转发给前端
        error -> sseEmitter.completeWithError(error), // 异常处理
        () -> sseEmitter.complete() // 结束处理
    );
```

**监听逻辑细化**：

    - **计费捕获**：监听器解析到 `event: done` 时，提取 `data.usage` 字段，异步触发 `UserAccountService.deduct()`。
    - **操作审计**：监听器解析到 `event: tool_start` 时，异步写入 `sys_operation_log`。
    - **安全熔断**：`doOnNext` 中若发现违规内容，直接抛出 `RuntimeException`。WebClient 会立即捕获该异常，触发 `completeWithError`，从而切断与 Python 的连接并向前端发送错误，实现**实时阻断**。



### 4. 异常处理与背压控制
#### 4.1 连接中断
+ **场景**：用户刷新页面或关闭浏览器。
+ **处理**：
    1. RuoYi 检测到前端 `IOException: Broken pipe`。
    2. RuoYi 立即调用 Python 的取消SSE API
    3. Python 端的 LangGraph 接收到断连信号，停止推理，避免浪费 Token。

#### 4.2 超时保活
+ **场景**：Python 执行 DeepSearch 深度搜索可能耗时 60秒+，期间没有数据产生。Nginx 可能会因为 60s 无响应而切断连接。
+ **协议**：
    - Python 端必须每隔 15秒 发送一个 `event: ping` 或空注释 `: keep-alive`。
    - RuoYi 收到后透传给前端，确保链路活跃。



### 5. 前端消费规范
前端不能简单使用 `EventSource`（因为它不支持 POST 请求体），建议使用 `fetch` + `ReadableStream` 或 `@microsoft/fetch-event-source` 库。

#### 渲染状态机 (UI State Machine)
前端需维护一个简易状态机来处理多变的事件流：

1. **Idle**：等待用户输入。
2. **Thinking**：收到 `tool_thinking`，显示“AI 思考中...”。
3. **Working**：收到 `tool_start`，显示工具卡片（加载态）。
4. **Updating**：收到 `message_chunk`，文本追加上屏。
5. **Finished**：收到 `done`，解锁输入框。

