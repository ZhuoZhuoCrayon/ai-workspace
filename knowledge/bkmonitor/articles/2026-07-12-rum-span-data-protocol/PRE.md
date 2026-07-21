
# 记录提前了解的内容

## 0x01 UA 解析【后台需支持】

| 字段                                                                                                                                    | 状态                                                       | 类型  | 描述                        | 备注                              |
| ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | --- | ------------------------- | ------------------------------- |
| `resource.user_agent.original`                                                                                                        | ![Backend](https://img.shields.io/badge/-backend-orange) | str | 客户端发送的 HTTP `User-Agent`。 | 如：`"Mozilla/5.0 ..."`。          |
| [`resource.device.manufacturer`](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/#device-manufacturer)         | ![Backend](https://img.shields.io/badge/-backend-orange) | str | 制造商名称（品牌）                 | `Apple`；`Samsung`               |
| [`resource.device.model.name`](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/#device-model-name)             | ![Backend](https://img.shields.io/badge/-backend-orange) | str | 型号的营销名称（机型）               | `iPhone 12`；`Samsung Galaxy S6` |
| [`resource.device.model.identifier`](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/#device-model-identifier) | ![Backend](https://img.shields.io/badge/-backend-orange) | str | 型号标识符                     | `iPhone3,4`; `SM-G920F`         |

**[1] resource.user_agent.original**：发送遥测请求，浏览器会自动携带 HTTP `User-Agent`，接收端应获取并填充到该字段。

**[2]  [Device](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)**：`Agegis` `DataDog` 均不会直接上报浏览器、设备信息，而是接收端根据 `User-Agent` 统一进行补充。
* Web：`Aegis` `DataDog` 均由后台通过 `User-Agent` 解析，SDK 不上报：[browser-rum-core/src/domain/view/viewCollection.ts](https://github.com/DataDog/browser-sdk/blob/main/packages/browser-rum-core/src/domain/view/viewCollection.ts)
* 客户端：端 SDK 上报


1）桌面浏览器

```text
Mozilla/5.0 (Windows NT 10.0; Win64; x64)
AppleWebKit/537.36 (KHTML, like Gecko)
Chrome/131.0.0.0 Safari/537.36
```

2）移动端——苹果

```text
Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)
AppleWebKit/605.1.15 (KHTML, like Gecko)
Version/17.5 Mobile/15E148 Safari/604.1
```

3）移动端——安卓

```text
Mozilla/5.0 (Linux; Android 14; SM-S918B)
AppleWebKit/537.36 (KHTML, like Gecko)
SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36
```

| 字段                                       | 桌面浏览器 | 移动端（苹果）    | 移动端（安卓）                  |
| ---------------------------------------- | ----- | ---------- | ------------------------ |
| `resource.device.manufacturer` *[1]*     | --    | Apple      | Samsung                  |
| `resource.device.model.name` *[2]*       | --    | iPhone 12  | SM-S918B                 |
| `resource.device.model.identifier` *[3]* | --    | iPhone13,2 | Samsung Galaxy S23 Ultra |

* *[1] 品牌
	* IOS：规定为 `Apple`
* *[2] 机型*
	* IOS：读取 `UIDevice.current.model`，例如 `iPhone`。
* *[3] 型号*
	* IOS：通过 `sysctl(CTL_HW, HW_MACHINE)` 获取，例如 `iPhone13,2`。
