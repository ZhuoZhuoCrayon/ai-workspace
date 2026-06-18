# Go 环境

## 0x01 切换流程

### a. 确认 gvm

`gvm` 是 `source ~/.gvm/scripts/gvm` 后才存在的 shell 函数，`which gvm` 查不到是正常现象。

判断是否安装看 `~/.gvm/scripts/gvm` 文件在不在，缺失时先询问是否安装。

参考 [gvm README](https://github.com/moovweb/gvm)：

```bash
bash < <(curl -s -S -L https://raw.githubusercontent.com/moovweb/gvm/master/binscripts/gvm-installer)
```

### b. 定位目标版本

从 `go.mod` 的 `go` 指令读取目标版本，归一为 `goX.Y[.Z]`。

```bash
sed -n 's/^go /go/p' go.mod | head -n 1   # go 1.23.0 -> go1.23.0
```

已装版本可能是两段 `go1.23` 或带补丁 `go1.23.0`，先列出已装版本，挑等于或最接近目标的那个。

```bash
ls ~/.gvm/gos                              # 或 source ~/.gvm/scripts/gvm && gvm list
```

### c. 组合执行

`source`、`gvm use` 和原命令写在同一条命令里。

```bash
source "$HOME/.gvm/scripts/gvm" && gvm use <version> && <command>
```

- `source` 不要放进管道，否则它在子 shell 里执行，切到的版本出了管道就失效。
- `gvm use` 只改当前 shell 的 `GOROOT`、`PATH`，跨多次命令调用不保留。

## 0x02 兜底与边界

### a. 直连二进制

`gvm` 函数加载不上时，绕开它直连目标版本的二进制（`gvm use` 本质就是改 `GOROOT`、`PATH`）。

```bash
GOROOT="$HOME/.gvm/gos/<version>" "$HOME/.gvm/gos/<version>/bin/go" <command>
```

### b. 验证输出

构建或测试输出多行、终端只回显末行时，把输出重定向到文件再读，避免漏看真正的报错。

### c. 版本未装

目标版本不在已装列表里时，先询问是否执行 `gvm install <version> -B`。

### d. 不可跳过

系统默认 Go 版本不匹配是切版本的场景，不是判定环境不可用或跳过、假装跳过编译、测试的理由。
