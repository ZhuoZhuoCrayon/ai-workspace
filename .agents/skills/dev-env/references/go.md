# Go 环境

## 0x01 检查表

安装：缺 `gvm` 或 `~/.gvm/scripts/gvm` 时，先询问是否安装。

参考：[gvm README](https://github.com/moovweb/gvm)

```bash
bash < <(curl -s -S -L https://raw.githubusercontent.com/moovweb/gvm/master/binscripts/gvm-installer)
```

版本：从 `go.mod` 的 `go` 指令读取，`1.22` 归一为 `go1.22`。

```bash
sed -n 's/^go /go/p' go.mod | head -n 1
```

运行：先加载 `gvm`，再切换版本并执行原命令。

```bash
source "$HOME/.gvm/scripts/gvm" && gvm use <version> && <command>
```

分支：

- 目标版本未安装：先询问是否执行 `gvm install <version> -B`。
- 禁止：不因系统默认 Go 版本不匹配跳过编译或测试。
