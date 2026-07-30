# Connecting an MCP client

metaseed ships a [Model Context Protocol](https://modelcontextprotocol.io) server that exposes its profiles, datasets, entities, ontology lookup, validation, and the [spec builder](spec-builder.md) as tools an AI assistant can call. This page covers connecting a client to it. For what the individual tools do, see the [Spec Builder MCP reference](../api/spec-builder-mcp.md) and [`metaseed mcp`](../api/cli.md).

The server runs locally against your own filesystem and specs. It is part of the `metaseed` package; metaseed-hub additionally hosts its own MCP endpoint over the hub's database, authenticated with personal access tokens — see the hub's documentation for that.

## The command

```bash
metaseed mcp                 # stdio (the default) — what clients use
metaseed mcp --transport http --port 8000   # HTTP, for debugging
```

`stdio` means the client starts the process itself and talks to it over standard input and output. There is nothing to start by hand and no port to manage.

## Claude Code

```bash
claude mcp add metaseed -- metaseed mcp
```

The `--` matters: everything after it is passed to the server untouched, so server flags are not read as Claude Code flags.

By default this registers the server for you in the current project. Use `--scope user` to make it available in every project, or `--scope project` to write a `.mcp.json` that you commit for collaborators:

```bash
claude mcp add --scope project metaseed -- metaseed mcp
```

```json
{
  "mcpServers": {
    "metaseed": {
      "type": "stdio",
      "command": "metaseed",
      "args": ["mcp"]
    }
  }
}
```

A committed `.mcp.json` prompts each collaborator for approval the first time they open the project, rather than silently launching a process from a cloned repository.

Verify the connection:

```bash
claude mcp list
claude mcp get metaseed
```

or run `/mcp` inside a session to see the server's status and the tools it offers.

## Claude Desktop

Add the same server to `claude_desktop_config.json` — on macOS at `~/Library/Application Support/Claude/`, on Windows at `%APPDATA%\Claude\`:

```json
{
  "mcpServers": {
    "metaseed": {
      "type": "stdio",
      "command": "metaseed",
      "args": ["mcp"]
    }
  }
}
```

Restart the app afterwards; it reads the file at startup.

## Without installing metaseed

`uvx` runs the server from PyPI in a throwaway environment, which suits trying it out:

```bash
claude mcp add metaseed -- uvx --from metaseed metaseed mcp
```

For regular use, install it so the command is stable and startup is not spent resolving the package:

```bash
uv tool install metaseed
```

## Troubleshooting

**"Failed to connect"** — the client could not start the process. Check that `metaseed mcp` runs in your shell; if it prints nothing and waits, that is correct, since a stdio server is silent until spoken to (Ctrl-C to exit). A `command not found` here means the client will not find it either: use an absolute path to the executable, or the `uvx` form above.

**The server connects but has no tools** — an older metaseed. Check with `metaseed --version` and upgrade.

**Errors mentioning a missing extra** — the adapter tools need their optional dependencies, for example `pip install "metaseed[pride]"`. The core dataset, profile, and spec-builder tools need nothing extra.

To see what the server is doing, run it in HTTP mode in a terminal (`metaseed mcp --transport http --port 8000`) and point the client at `http://localhost:8000/mcp`; its output then goes to your terminal instead of down the stdio pipe.
