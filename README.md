# Devstack Jira + Confluence MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI assistants (Claude, Cursor, etc.) to your **on-premises Devstack Jira and Confluence** instances.

---

## Features

- **Jira tools** — search issues, create/update/transition/delete, manage comments, worklogs, attachments, sprints, and boards
- **Confluence tools** — search, read/create/update/delete pages and blog posts, manage comments, labels, and attachments
- **Guardrails** — three operating modes (`readonly`, `workshop`, `full`) and a per-tool allowlist to restrict what the AI can do
- **On-premises support** — works with any Devstack Jira/Confluence URL (not restricted to `atlassian.net`)
- **Auth** — Basic authentication (username + Personal Access Token or password)

---

## Requirements

- Node.js ≥ 18
- Access to a Devstack Jira and Confluence instance over HTTPS

---

## Installation

```bash
npm install
npm run build
```

---

## Configuration

Set the following environment variables before starting the server:

| Variable | Required | Description |
|---|---|---|
| `DEVSTACK_JIRA_BASE_URL` | ✅ | Jira base URL, e.g. `https://jira.example.com` |
| `DEVSTACK_CONFLUENCE_BASE_URL` | ✅ | Confluence base URL, e.g. `https://confluence.example.com` |
| `DEVSTACK_USERNAME` | ✅ | Your Devstack username |
| `DEVSTACK_TOKEN` | ✅ | Personal Access Token or password |
| `DEVSTACK_MODE` | | `readonly` (default), `workshop`, or `full` |
| `DEVSTACK_TOOLS` | | Comma-separated allowlist of tool names (overrides mode) |
| `DEVSTACK_FILE_ROOT` | | Local directory from which attachments may be read/written |

### Operating Modes

| Mode | What's available |
|---|---|
| `readonly` (default) | All read/search tools only |
| `workshop` | Read tools + `jira_create_issue`, `jira_add_comment`, `confluence_add_comment` |
| `full` | All tools including update, delete, transition, upload |

---

## Running

```bash
# stdio mode (for MCP clients like Claude Desktop)
npm start
```

---

## MCP Client Configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "devstack": {
      "command": "node",
      "args": ["/path/to/Devstack_Jira_Conf_MCP_Server/dist/index.js"],
      "env": {
        "DEVSTACK_JIRA_BASE_URL": "https://jira.example.com",
        "DEVSTACK_CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "DEVSTACK_USERNAME": "your-username",
        "DEVSTACK_TOKEN": "your-pat-or-password",
        "DEVSTACK_MODE": "workshop"
      }
    }
  }
}
```

---

## Available Tools

### Jira

| Tool | Mode | Description |
|---|---|---|
| `jira_myself` | readonly | Get authenticated user |
| `jira_list_projects` | readonly | List Jira projects |
| `jira_get_project` | readonly | Get a project by key/id |
| `jira_list_issue_types` | readonly | List issue types for a project |
| `jira_list_priorities` | readonly | List all priorities |
| `jira_list_statuses` | readonly | List all statuses |
| `jira_search_users` | readonly | Search users by name/email |
| `jira_search_issues` | readonly | Search issues with JQL |
| `jira_get_issue` | readonly | Get a single issue |
| `jira_get_transitions` | readonly | Get available transitions |
| `jira_list_comments` | readonly | List issue comments |
| `jira_list_attachments` | readonly | List issue attachments |
| `jira_list_link_types` | readonly | List link types |
| `jira_list_worklogs` | readonly | List issue worklogs |
| `jira_list_versions` | readonly | List project versions |
| `jira_list_components` | readonly | List project components |
| `jira_list_boards` | readonly | List Scrum/Kanban boards |
| `jira_get_board_backlog` | readonly | Get board backlog |
| `jira_list_sprints` | readonly | List sprints for a board |
| `jira_get_sprint_issues` | readonly | Get issues in a sprint |
| `jira_create_issue` | workshop | Create an issue |
| `jira_add_comment` | workshop | Add a comment |
| `jira_update_issue` | full | Update an issue |
| `jira_transition_issue` | full | Transition an issue |
| `jira_delete_issue` | full | Delete an issue |
| `jira_update_comment` | full | Update a comment |
| `jira_add_worklog` | full | Log time on an issue |
| `jira_link_issues` | full | Link two issues |
| `jira_assign_issue` | full | Assign an issue |
| `jira_upload_attachment` | full | Upload a file attachment |

### Confluence

| Tool | Mode | Description |
|---|---|---|
| `confluence_list_spaces` | readonly | List spaces |
| `confluence_get_space` | readonly | Get a space by key |
| `confluence_search` | readonly | Search with CQL |
| `confluence_search_content` | readonly | Search content by title/type/space |
| `confluence_get_page` | readonly | Get a page with body |
| `confluence_get_page_children` | readonly | List child pages |
| `confluence_get_page_ancestors` | readonly | Get ancestor chain |
| `confluence_list_page_versions` | readonly | List page versions |
| `confluence_list_comments` | readonly | List page comments |
| `confluence_get_page_labels` | readonly | Get page labels |
| `confluence_list_page_attachments` | readonly | List page attachments |
| `confluence_add_comment` | workshop | Add a comment |
| `confluence_create_page` | full | Create a page |
| `confluence_update_page` | full | Update a page |
| `confluence_delete_page` | full | Delete a page |
| `confluence_create_blogpost` | full | Create a blog post |
| `confluence_add_page_labels` | full | Add labels to a page |
| `confluence_upload_attachment` | full | Upload a file attachment |

---

## Development

```bash
npm run dev   # watch mode
npm test      # build + run guardrails tests
```

---

## License

MIT 
