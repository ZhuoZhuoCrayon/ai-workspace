# 资源加载时序

本文对照 W3C Resource Timing、Chrome Timing 和 web.dev，并给出 Resource Span 请求时序的产品划分。适用范围是单次 `resource` Span 的阶段图，不含 View 导航瀑布。

阶段名称靠近 Chrome Timing。每段时长用已上报的 `attributes.resource.*.duration` 计算，起点用对应的 `start`，单位为毫秒，相对该资源 `startTime`。

## 0x01 W3C Resource Timing

规范记录的是时间点，不是产品上的色块。浏览器按发生顺序打点，产品上的每一段是相邻两点相减。来源：[Resource Timing](https://www.w3.org/TR/resource-timing/)。

| 顺序 | 时间点 | 含义 |
| --- | --- | --- |
| 1 | `startTime` | 这次取资源开始 |
| 2 | `redirectStart` | 第一次重定向开始 |
| 3 | `redirectEnd` | 最后一次重定向的响应收完 |
| 4 | `workerStart` | Service Worker 开始处理这次请求；未拦截时为 `0` |
| 5 | `fetchStart` | 重定向结束后，开始取最终资源 |
| 6 | `domainLookupStart` | DNS 查询开始 |
| 7 | `domainLookupEnd` | DNS 查询结束 |
| 8 | `connectStart` | 开始建立到服务器的连接 |
| 9 | `secureConnectionStart` | TLS 握手开始；非 HTTPS 时为 `0` |
| 10 | `connectEnd` | 连接建立完成，TLS 包含在内 |
| 11 | `requestStart` | 开始向服务器发请求 |
| 12 | `firstInterimResponseStart` | 中间响应，例如 `103` |
| 13 | `responseStart` | 收到响应首字节 |
| 14 | `finalResponseHeadersStart` | 最终响应头开始，通常是 `200` |
| 15 | `responseEnd` | 最后一字节到达，或连接先关闭 |

用上面的时间点可以算出这些耗时：

| 顺序 | 耗时 | 计算 |
| --- | --- | --- |
| 1 | 重定向 | `redirectEnd − redirectStart` |
| 2 | Service Worker | `fetchStart − workerStart` |
| 3 | DNS | `domainLookupEnd − domainLookupStart` |
| 4 | 建立连接（含 TLS） | `connectEnd − connectStart` |
| 5 | TLS 握手 | `connectEnd − secureConnectionStart` |
| 6 | 发出请求后等到首字节 | `responseStart − requestStart` |
| 7 | 接收响应体 | `responseEnd − responseStart` |

规范没有排队时间点。跨源资源未通过 Timing-Allow-Origin 检查时，重定向到 `responseStart` 之间的点会变成 `0`，只保留 `startTime`、`fetchStart`、总时长和 `responseEnd`。

`workerStart` 是重定向链最终请求上的 Service Worker 开始时间。`fetchStart` 是 post-redirect start。产品上的「后台脚本处理」发生在重定向之后。

## 0x02 Chrome Timing

Chrome 开发者工具中，点开一条请求的 Timing。一次请求不会出现全部标签。来源：[Chrome 网络面板说明](https://developer.chrome.com/docs/devtools/network/reference)。

| 顺序 | Timing 标签 | 含义 |
| --- | --- | --- |
| 1 | Queueing | 连接开始前排队：存在更高优先级请求，或同一源连接数已满 |
| 2 | Stalled | 连接开始后仍可能因 Queueing 同类原因停滞 |
| 3 | DNS Lookup | 解析域名对应的 IP |
| 4 | Initial connection | 建立连接，包含 TCP 握手和 TLS，不单列 TLS |
| 5 | Proxy negotiation | 与代理协商，仅走代理时出现 |
| 6 | Request sent | 正在发送 HTTP 请求 |
| 7 | ServiceWorker Preparation | 正在启动 Service Worker |
| 8 | Request to ServiceWorker | 请求交给 Service Worker |
| 9 | Waiting (TTFB) | 请求已发出，等待响应首字节。包含一趟网络往返和服务器准备时间 |
| 10 | Content Download | 读取响应体 |

常见可见：Queueing、DNS Lookup、Initial connection、Waiting (TTFB)、Content Download。连接已建立时，DNS Lookup 和 Initial connection 经常为 `0`。

Chrome 不单独上报 Queueing / Stalled / Request sent 到 RUM 字段，产品阶段图无法画出这三行。

## 0x03 Google web.dev

web.dev 讲解同一组时间点，并单独定义页面导航的 Time to First Byte（TTFB，首字节时间）。来源：[Navigation and Resource Timing](https://web.dev/articles/navigation-and-resource-timing)、[TTFB](https://web.dev/articles/ttfb)。

| 顺序 | 阶段 | 时间点 | 含义 |
| --- | --- | --- | --- |
| 1 | Redirects | `redirectStart` / `redirectEnd` | HTTP 重定向 |
| 2 | DNS lookup | `domainLookupStart` / `domainLookupEnd` | DNS 解析 |
| 3 | Connection | `connectStart` → `secureConnectionStart` → `connectEnd` | 建连，HTTPS 时包含 TLS，TLS 耗时 = `connectEnd − secureConnectionStart` |
| 4 | Fetch | `fetchStart` | 开始取资源，会先查缓存 |
| 5 | Service worker | `workerStart` | 未拦截时为 `0` |
| 6 | Request | `requestStart` → `responseStart` | 发出请求到收到首字节 |
| 7 | Response | `responseStart` → `responseEnd` | 接收响应体 |

web.dev 的页面 TTFB 从导航开始算到 `responseStart`，包含：

1. 重定向
2. Service Worker 启动（如有）
3. DNS
4. 建连和 TLS
5. 发出请求直到首字节到达

Chrome Timing 的 Waiting (TTFB) 只等于第 `5` 项。Resource Span 的「等待首字节」跟 Chrome 这一行走，对应 `resource.first_byte.duration`。

## 0x04 产品建议

始终展示查找服务器、建立连接、加密连接、等待首字节、下载内容。上报了重定向或 Service Worker 时，再增加对应行。

时长用 `resource.*.duration`。建立连接需要减去 TLS：W3C 的 `connectEnd − connectStart` 已包含加密，直接展示完整 `connect.duration` 会和下一行重复。无 `ssl` 时使用完整 `connect.duration`。

### a. 阶段与计算

| 顺序 | 产品名 | 出现条件 | 时长 |
| --- | --- | --- | --- |
| 1 | 重定向 | 上报了 `redirect.start` 和 `redirect.duration` | `attributes.resource.redirect.duration` |
| 2 | 后台脚本处理 | 上报了 `worker.start` 和 `worker.duration` | `attributes.resource.worker.duration` |
| 3 | 查找服务器 | 始终占一行 | `attributes.resource.dns.duration` |
| 4 | 建立连接 | 始终占一行 | 有 `ssl` 时：`connect.duration − ssl.duration`<br />无 `ssl` 时：`connect.duration` |
| 5 | 加密连接 | 始终占一行 | `attributes.resource.ssl.duration` |
| 6 | 等待首字节 | 始终占一行 | `attributes.resource.first_byte.duration` |
| 7 | 下载内容 | 始终占一行 | `attributes.resource.download.duration` |

时间轴上，建立连接画到 `ssl.start`，加密连接从 `ssl.start` 画到 `connect` 结束。

### b. 说明与用户感受

| 阶段 | 说明 | 用户感受 |
| --- | --- | --- |
| 重定向 | [a] 浏览器跟随 HTTP 重定向，直到拿到最终 URL，对应 `redirectEnd − redirectStart`<br />[b] 未发生重定向时不上报 | [a] 目标内容还没开始出现<br />[b] 文档请求会延长白屏，接口请求会延长 loading |
| 后台脚本处理 | [a] Service Worker 拦截并处理该请求的时间，对应 `fetchStart − workerStart`<br />[b] 记录的是重定向之后、最终请求上的处理<br />[c] 未拦截时不上报 | [a] 界面没有单独提示<br />[b] 用户只会感到这次加载更慢，无法分辨是后台脚本在处理 |
| 查找服务器 | [a] DNS 解析耗时，对应 `domainLookupEnd − domainLookupStart`<br />[b] 解析结果已缓存、或未发起新查询时，可能为 `0` 或不上报 | [a] 内容尚未出现<br />[b] 用户无法感知「正在解析域名」，体验上仍是点了之后没有反应 |
| 建立连接 | [a] 传输连接中扣除 TLS 后的部分<br />[b] W3C 的 `connectEnd − connectStart` 包含加密，产品用 `connect.duration − ssl.duration`，避免与下一行重复 | [a] 内容尚未出现<br />[b] 用户无法感知「正在建连」，体验上仍是在等待 |
| 加密连接 | [a] TLS 握手，对应 `connectEnd − secureConnectionStart`<br />[b] 非 HTTPS、或未发生新握手时不上报 | [a] 内容尚未出现<br />[b] 用户无法感知「正在握手」，体验上仍是在等待 |
| 等待首字节 | [a] 从发出请求到收到响应首字节，对应 `responseStart − requestStart`<br />[b] 包含网络往返和服务端处理，浏览器时序无法拆分<br />[c] 对齐 Chrome Waiting (TTFB)，范围小于 web.dev 的页面 TTFB | [a] 本次请求的内容仍不可见：页面持续白屏或停留在旧画面，接口持续 loading<br />[b] 过慢时会感觉页面没有反应 |
| 下载内容 | [a] 从收到首字节到响应体接收完毕，对应 `responseEnd − responseStart`<br />[b] 耗时主要随体积和带宽变化 | [a] 内容开始出现并逐渐完整，图片、脚本会陆续可见<br />[b] 接口数据会从空状态填到页面上<br />[c] 体积大时，用户能感到「出来了但还在加载」 |

等待首字节拆不开服务端处理与网络往返。要判断服务端是否慢，需要结合 Trace 或 [Server Timing](https://www.w3.org/TR/server-timing/)。

### c. 缺数字段

| 上报情况 | 页面展示 |
| --- | --- |
| `start` 与 `duration` 都在，且 `duration > 0` | 显示毫秒数，画出色块 |
| `start` 与 `duration` 都在，且 `duration = 0` | 写 `0` 毫秒。该步骤没有额外耗时 |
| 缺少 `start` 或 `duration` | 写「没有上报」，不画色块。可能该步骤未发生，也可能跨源不允许查看细分时间 |

查找服务器、建立连接、加密连接都没有上报时，写「没有上报」。跨源资源未暴露细分时间时表现相同，不能据此判断连接复用。

## 0x05 参考资料

| 来源 | 文档 |
| --- | --- |
| W3C | [Resource Timing](https://www.w3.org/TR/resource-timing/) |
| W3C | [Server Timing](https://www.w3.org/TR/server-timing/) |
| Chrome | [网络面板 · Timing](https://developer.chrome.com/docs/devtools/network/reference) |
| web.dev | [Navigation and Resource Timing](https://web.dev/articles/navigation-and-resource-timing) |
| web.dev | [Time to First Byte](https://web.dev/articles/ttfb) |
