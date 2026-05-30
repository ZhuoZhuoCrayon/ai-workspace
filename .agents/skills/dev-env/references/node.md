# Node.js 环境

## 0x01 检查表

安装：缺 `nvm` 或 `${NVM_DIR:-$HOME/.nvm}/nvm.sh` 时，先询问是否安装。

参考：[nvm README](https://github.com/nvm-sh/nvm)

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
```

版本优先级：

1. `.nvmrc`
2. `package.json` 的 `engines.node`
3. 用户明确指定的版本

包管理器优先级：

1. `pnpm-lock.yaml`
2. `yarn.lock`
3. `package-lock.json`
4. 项目已有脚本或用户指定命令

运行：非交互 shell 先加载 `nvm`。

```bash
source "${NVM_DIR:-$HOME/.nvm}/nvm.sh" && nvm use <version> && <command>
```

分支：

- 目标版本未安装：先询问是否执行 `nvm install <version>`。
- 禁止：不绕过项目声明版本直接使用系统 Node.js。
