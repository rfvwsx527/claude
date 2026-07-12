# Obsidian MCP 配置

本仓库包含 Claude Code 的 Obsidian MCP 服务器配置（`.mcp.json`），通过 [mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian) 连接 Obsidian 的 Local REST API 插件。

## 前置条件

1. 在 Obsidian 中安装并启用 **Local REST API** 社区插件
2. 在插件设置中复制 API Key（默认端口为 `27124`，HTTPS）
3. 本机已安装 [uv](https://docs.astral.sh/uv/)（提供 `uvx` 命令）

## 使用方式

### 方式一：项目配置（本仓库已内置）

在本仓库目录下启动 Claude Code 时，`.mcp.json` 会自动加载 obsidian 服务器。API Key 不会提交到仓库，通过环境变量注入：

```bash
export OBSIDIAN_API_KEY=你的key
# 可选，默认值如下
export OBSIDIAN_HOST=127.0.0.1
export OBSIDIAN_PORT=27124

claude
```

### 方式二：全局/本地添加（命令行）

```bash
claude mcp add obsidian \
  -e OBSIDIAN_API_KEY=你的key \
  -e OBSIDIAN_HOST=127.0.0.1 \
  -e OBSIDIAN_PORT=27124 \
  -- uvx mcp-obsidian
```

加 `-s user` 可对所有项目生效；加 `-s project` 则写入项目的 `.mcp.json`。

## 验证

启动 Claude Code 后运行 `/mcp`，确认 `obsidian` 服务器状态为 connected。

## 注意事项

- **不要把真实的 API Key 提交到仓库**，请始终通过环境变量或 `claude mcp add -e` 传入。
- 该服务器连接的是 `127.0.0.1`（你本机的 Obsidian），因此只在本地运行 Claude Code 时可用；在云端/远程会话中无法访问你本机的 Obsidian。
