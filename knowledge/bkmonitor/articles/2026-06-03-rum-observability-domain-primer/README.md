---
title: RUM 领域信息收集：核心术语、机制与规范索引
tags: [rum, observability, web-vitals, performance-timeline, trace-context, opentelemetry]
description: 按规范聚合整理 RUM 领域常见术语、机制解释和参考链接，作为领域入门资料。
created: 2026-06-03
updated: 2026-06-03
---

# RUM 领域信息收集：核心术语、机制与规范索引

本文按规范和标准聚合整理 RUM（真实用户监控）领域的核心术语、机制和参考链接，适合作为领域建设的入门资料。

本文不追求名词罗列，而是帮助你建立一个最小认知框架：概念属于哪类规范、解决什么问题、彼此如何衔接。

## 0x01 领域基础概念

### a. 规范概览

这一组概念不对应单一标准，而是 RUM 和可观测性领域的通用基础词汇。

它们描述用户访问过程、观测数据形态和前端应用形态，是后续阅读各类规范的前提。

建设时先统一这组词的含义，才能避免指标口径、文档表述和系统设计各说各话。

### b. 核心术语

- Real User Monitoring（真实用户监控，RUM）：直接采集真实用户在浏览器或客户端上的性能、错误、行为和环境数据，用来衡量真实体验。
- Observability（可观测性）：通过指标、日志、追踪等信号理解系统内部状态，并支持定位问题。
- Telemetry（遥测）：系统主动上报的观测数据总称，通常包含 `metrics`、`logs`、`traces` 和 `events`。
- Session（会话）：一段连续的用户访问过程，常用于串联页面浏览、接口调用、错误和行为路径。
- Page View（页面浏览）：用户打开一个页面或一次路由切换产生的浏览记录。
- Single-Page Application（单页应用，SPA）：主要通过前端路由切换视图的应用形态，RUM 中尤其关注路由切换性能。

### c. 参考链接

- 行业概览：[Web Vitals](https://web.dev/vitals/)
- 可观测规范：[OpenTelemetry 文档](https://opentelemetry.io/docs/)

## 0x02 Web Vitals 与 Core Web Vitals

### a. 规范概览

这一组指标从用户感知出发，回答页面是否加载够快、交互是否流畅和布局是否稳定。

它们是 RUM 仪表盘和体验目标最常见的指标入口。

建设时通常先围绕这组指标确定体验目标、告警阈值和优化优先级。

### b. 核心术语

- Web Vitals（网页体验指标）：Google 提出的一组以用户体验为中心的前端性能指标集合。
- Core Web Vitals（核心网页指标）：Web Vitals 中被重点用于衡量体验质量的一组核心指标。
- Largest Contentful Paint（最大内容绘制，LCP）：页面主要内容完成呈现所花的时间，衡量「页面何时基本加载完成」。
- Interaction to Next Paint（下次绘制交互延迟，INP）：用户交互到界面完成下一次可见反馈的延迟，衡量交互响应性。
- Cumulative Layout Shift（累积布局偏移，CLS）：页面加载和使用过程中元素意外跳动的程度，衡量视觉稳定性。
- First Contentful Paint（首次内容绘制，FCP）：页面第一次绘制出文本、图片、SVG 等实际内容的时间。
- Time to First Byte（首字节时间，TTFB）：浏览器发起请求后收到服务端第一个字节的时间，反映网络和后端首包响应速度。

### c. 参考链接

- Web Vitals：[web.dev/vitals](https://web.dev/vitals/)

## 0x03 W3C Performance Timeline 系列

### a. 规范概览

这一组规范定义浏览器如何统一暴露性能条目。

RUM SDK 采集导航、资源、绘制和交互信息时，通常都要从这套机制切入。

建设时理解这套机制，可以帮助你判断哪些数据浏览器原生可取，哪些数据需要额外埋点补齐。

### b. 核心术语

- Performance Timeline（性能时间线）：浏览器统一暴露各类性能条目的机制，RUM SDK 通常通过它读取性能数据。
- PerformanceEntry（性能条目）：性能时间线中的一条记录，可能代表导航、资源、绘制、事件等对象。
- PerformanceObserver（性能观察器）：用于订阅性能条目的浏览器接口，是 RUM 采集 Web 性能指标的核心机制。

### c. 参考链接

- Performance Timeline：[W3C Performance Timeline](https://www.w3.org/TR/performance-timeline/)

## 0x04 W3C Navigation Timing

### a. 规范概览

这一组规范把一次页面导航拆成多个网络和加载阶段，适合回答「页面慢在跳转前后的哪个阶段」。

它是页面加载分析最基础的时间分解来源。

建设时它常用于拆解首屏慢、页面打开慢和路由切换慢的根因归属。

### b. 核心术语

- Navigation Timing（导航计时）：描述一次页面导航从跳转、DNS、TCP、请求、响应到页面加载各阶段耗时的数据模型。
- DOMContentLoaded（DOM 完成解析事件）：HTML 解析完成、DOM 构建结束的时间点。
- Load Event（页面加载完成事件）：页面及依赖资源完成加载后的时间点。

### c. 参考链接

- Navigation Timing Level 2：[W3C Navigation Timing Level 2](https://www.w3.org/TR/navigation-timing-2/)

## 0x05 W3C Resource Timing

### a. 规范概览

这一组规范面向静态资源加载分析，适合回答「慢的是页面本身，还是某个 JS、CSS、图片或字体资源」。

它常用于发现慢资源、失败资源和 CDN 异常。

建设时它直接决定你能否把页面问题下钻到具体资源、域名和缓存链路。

### b. 核心术语

- Resource Timing（资源计时）：记录 JS、CSS、图片、字体等静态资源的加载耗时。
- PerformanceResourceTiming（资源性能条目）：单个资源的网络阶段信息，可用于分析慢资源、失败资源和 CDN 问题。

### c. 参考链接

- Resource Timing Level 2：[W3C Resource Timing Level 2](https://www.w3.org/TR/resource-timing-2/)

## 0x06 W3C Paint、LCP、Layout、Event 和 Long Tasks

### a. 规范概览

这一组规范共同回答 `3` 类问题：页面何时开始显示内容、页面为什么会抖动或卡顿、用户交互何时得到可见反馈。

它们构成 `FCP`、`LCP`、`CLS`、`INP` 和长任务分析的底层机制。

建设时这组规范最值得优先打通，因为用户对「慢」「卡」「抖」的主观感受基本都落在这里。

### b. 核心术语

- Paint Timing（绘制计时）：定义首绘等「页面何时开始显示内容」的时间点。
- First Paint（首次绘制，FP）：浏览器第一次发生像素输出的时间。
- First Contentful Paint（首次内容绘制，FCP）：第一次出现实际内容的时间。
- Largest Contentful Paint（最大内容绘制，LCP）：最大可见内容元素完成绘制的时间。
- Layout Instability（布局不稳定性）：用于衡量页面元素非预期位移的机制，是 CLS 的基础。
- Cumulative Layout Shift（累积布局偏移，CLS）：对布局抖动进行累计评分的指标。
- Event Timing（事件计时）：衡量用户输入事件处理和视觉反馈延迟的机制，是 INP 的基础。
- Interaction to Next Paint（下次绘制交互延迟，INP）：从交互到下一次可见绘制的延迟统计指标。
- Long Task（长任务）：主线程上执行时间过长、阻塞交互和渲染的任务，通常指超过 `50 ms`。
- Long Tasks API（长任务接口）：用于发现前端主线程卡顿来源的浏览器 API。

### c. 参考链接

- Paint Timing：[W3C Paint Timing](https://www.w3.org/TR/paint-timing/)
- Largest Contentful Paint：[W3C Largest Contentful Paint](https://www.w3.org/TR/largest-contentful-paint/)
- Layout Instability：[W3C Layout Instability](https://www.w3.org/TR/layout-instability/)
- Event Timing：[W3C Event Timing](https://www.w3.org/TR/event-timing/)
- Long Tasks API：[W3C Long Tasks API](https://www.w3.org/TR/longtasks-1/)

## 0x07 W3C Server Timing

### a. 规范概览

这一组规范让服务端把内部阶段耗时显式暴露给浏览器。

RUM 使用它时，可以把页面慢和后端阶段慢直接关联起来。

建设时接入这组能力，可以减少前后端对性能归因的扯皮成本。

### b. 核心术语

- Server-Timing（服务端计时）：服务端通过响应头把内部阶段耗时暴露给浏览器，帮助前后端联合定位性能瓶颈。
- Metric（服务端阶段指标）：通过响应头携带的单个耗时项，例如应用处理、缓存命中和数据库耗时。

### c. 参考链接

- Server-Timing：[W3C Server-Timing](https://www.w3.org/TR/server-timing/)

## 0x08 W3C Trace Context 与 Baggage

### a. 规范概览

这组规范解决的是「链路标识和少量业务上下文如何跨前后端传播」。

在 RUM 场景里，它们不只用于把前端请求串到后端 Trace，也用于让页面体验问题顺着同一条链路追到接口、服务和版本。

建设时如果不尽早统一这组传播协议，前端体验问题通常只能停留在页面层，很难进入后端归因闭环。

### b. 核心术语

- Distributed Tracing（分布式追踪）：用统一标识把跨前后端、跨服务的一次请求链路串起来。
- Trace（追踪链路）：一次端到端请求经过多个系统时形成的完整调用链。
- Span（调用片段）：调用链中的一个局部操作，例如一次 HTTP 请求或一次函数执行。
- Trace Context（追踪上下文）：在 HTTP 等协议中跨进程传播链路标识的标准机制。
- traceparent（追踪父上下文头）：承载 `trace id`、`parent id` 和采样标记等核心字段的标准请求头。
- tracestate（追踪状态头）：承载厂商扩展链路状态的标准请求头。
- Baggage（透传业务上下文）：用于跨服务附带少量业务维度信息，例如租户、版本和实验分组。

### c. 参考链接

- Trace Context：[W3C Trace Context](https://www.w3.org/TR/trace-context/)
- Baggage：[W3C Baggage](https://www.w3.org/TR/baggage/)

## 0x09 OpenTelemetry

### a. 规范概览

这一组规范定义现代可观测系统如何组织采集、字段命名和上下文传播。

RUM 落地时，它常作为前端、后端和平台数据对齐的共同语言。

建设时越早对齐这套语义约定，后续跨团队、跨系统的数据整合成本越低。

### b. 核心术语

- OpenTelemetry（开放遥测）：当前业界最主流的可观测标准体系之一，定义采集、语义和上下文传播。
- Signal（观测信号）：一类观测数据，例如指标、日志和追踪。
- Traces（追踪）：用于表达请求链路和耗时结构的数据。
- Metrics（指标）：聚合后的数值观测信号，例如请求量、错误率和耗时分位数。
- Logs（日志）：离散事件记录，适合保存详细上下文。
- Semantic Conventions（语义约定）：对字段名和属性含义进行标准化，保证不同系统数据可对齐。
- Context Propagation（上下文传播）：在进程、线程和网络调用之间传递 trace 与业务上下文的机制。

### c. 参考链接

- OpenTelemetry Specifications：[OpenTelemetry Specifications](https://opentelemetry.io/docs/specs/)

## 0x10 上报与采集机制

### a. 规范概览

这一组机制更偏工程落地。

它们分别回答 `3` 个问题：数据怎么安全上报、如何控制成本、错误位置如何还原到源码。

建设时这组机制直接影响 SDK 复杂度、数据成本和错误定位效率。

### b. 核心术语

- Beacon API（信标上报接口）：浏览器提供的轻量异步上报机制，适合页面卸载前发送 RUM 数据。
- Sampling（采样）：只上报部分数据以控制成本和存储量。
- Head Sampling（头部采样）：在链路开始时决定是否采样。
- Tail Sampling（尾部采样）：在看到更完整结果后再决定是否保留链路。
- Source Map（源码映射）：将压缩混淆后的前端代码位置还原到源代码文件和行列，便于错误定位。

### c. 参考链接

- Beacon API：[W3C Beacon API](https://www.w3.org/TR/beacon/)
- Source Map：[Source Map Revision 3 Proposal](https://sourcemaps.info/spec.html)

## 0x11 稳定性常见术语

### a. 规范概览

这一组术语更偏工程实践，不完全对应单一标准。

它们描述 RUM 在错误和故障治理中最常见的问题类型和统计口径。

建设时需要尽早定义这些问题的识别规则和统计口径，否则错误治理很难稳定落地。

### b. 核心术语

- JavaScript Error（JavaScript 异常）：运行时抛出的错误，通常通过 `error` 事件或全局异常钩子采集。
- Unhandled Rejection（未处理的 Promise 拒绝）：Promise 异步错误未被捕获时产生的异常事件。
- Resource Load Error（资源加载错误）：图片、脚本、样式等资源加载失败导致的问题。
- White Screen（白屏）：页面未正常渲染出有效内容的故障现象，通常需要工程化规则检测。
- Crash Rate（崩溃率）：页面或应用不可恢复故障在会话中的占比。
- Error Rate（错误率）：错误事件数或出错会话数占总体的比例。

### c. 参考链接

- JavaScript Error：[MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/error_event)
- Unhandled Rejection：[MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/unhandledrejection_event)
- Resource Load Error：[MDN](https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/error_event)
- 其他术语：`White Screen`、`Crash Rate` 和 `Error Rate` 更偏工程实践概念，没有统一的单一标准。

## 0x12 参考

### a. 体验指标与浏览器性能

- [Web Vitals](https://web.dev/vitals/)
- [Performance Timeline](https://www.w3.org/TR/performance-timeline/)
- [Navigation Timing Level 2](https://www.w3.org/TR/navigation-timing-2/)
- [Resource Timing Level 2](https://www.w3.org/TR/resource-timing-2/)
- [Paint Timing](https://www.w3.org/TR/paint-timing/)
- [Largest Contentful Paint](https://www.w3.org/TR/largest-contentful-paint/)
- [Layout Instability](https://www.w3.org/TR/layout-instability/)
- [Event Timing](https://www.w3.org/TR/event-timing/)
- [Long Tasks API](https://www.w3.org/TR/longtasks-1/)
- [Server-Timing](https://www.w3.org/TR/server-timing/)

### b. 链路传播与可观测标准

- [Trace Context](https://www.w3.org/TR/trace-context/)
- [Baggage](https://www.w3.org/TR/baggage/)
- [OpenTelemetry Specifications](https://opentelemetry.io/docs/specs/)

### c. 上报与错误治理

- [Beacon API](https://www.w3.org/TR/beacon/)
- [Source Map Revision 3 Proposal](https://sourcemaps.info/spec.html)
- [MDN error](https://developer.mozilla.org/en-US/docs/Web/API/Window/error_event)
- [MDN unhandledrejection](https://developer.mozilla.org/en-US/docs/Web/API/Window/unhandledrejection_event)
- [MDN HTMLElement error](https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/error_event)
