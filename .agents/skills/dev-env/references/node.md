# Node.js 环境

## 0x01 切换流程

### a. 确认 nvm

`nvm` 是 `source` 进来的 shell 函数，`which nvm` 查不到是正常现象。

判断是否安装看 `${NVM_DIR:-$HOME/.nvm}/nvm.sh` 文件在不在，缺失时先询问是否安装。

参考 [nvm README](https://github.com/nvm-sh/nvm)：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
```

### b. 定位 Node 版本

按优先级取目标版本：

1. `.nvmrc`
2. `package.json` 的 `engines.node`
3. 用户明确指定的版本

### c. 选包管理器

按优先级选包管理器：

1. `pnpm-lock.yaml`
2. `yarn.lock`
3. `package-lock.json`
4. 项目已有脚本或用户指定命令

### d. 组合执行

`source`、`nvm use` 和原命令写在同一条命令里。

```bash
source "${NVM_DIR:-$HOME/.nvm}/nvm.sh" && nvm use <version> && <command>
```

- `source` 不要放进管道，否则它在子 shell 里加载，切到的版本出了管道就失效。
- 列已装版本用 `source ... && nvm ls` 或 `ls ~/.nvm/versions/node`。

## 0x02 兜底与边界

### a. 直连二进制

`nvm` 函数加载不上时，把目标版本的 `bin` 目录前置到 `PATH`。

```bash
PATH="$HOME/.nvm/versions/node/<version>/bin:$PATH" <command>
```

### b. 版本未装

目标版本不在已装列表里时，先询问是否执行 `nvm install <version>`。

### c. 不绕过系统版本

始终用项目声明的版本，不直接使用系统 Node.js。
