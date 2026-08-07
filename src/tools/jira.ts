import type { DevstackClient } from "../devstack-client.js";
import type { ToolDef } from "./types.js";

const enc = encodeURIComponent;

// Plain text → simple Jira wiki-markup paragraph (API v2 uses wiki markup or plain body)
function plainBody(text: string) {
  return text;
}

export function buildJiraTools(client: DevstackClient): ToolDef[] {
  return [
    // ─── meta / discovery ─────────────────────────────────────────────
    {
      name: "jira_myself",
      description: "Return the authenticated Jira account (sanity-check auth).",
      inputSchema: { type: "object", properties: {} },
      handler: async () => client.jiraGet("/rest/api/2/myself"),
    },
    {
      name: "jira_list_projects",
      description: "List Jira projects (paginated). Optional: query (search), maxResults, startAt.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Filter projects by name or key" },
          maxResults: { type: "number", description: "Max results (default 50)" },
          startAt: { type: "number", description: "Pagination offset (default 0)" },
        },
      },
      handler: async (a) =>
        client.jiraGet("/rest/api/2/project/search", {
          query: a.query,
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_get_project",
      description: "Fetch a single Jira project by key or id.",
      inputSchema: {
        type: "object",
        properties: { projectKeyOrId: { type: "string" } },
        required: ["projectKeyOrId"],
      },
      handler: async (a) => client.jiraGet(`/rest/api/2/project/${enc(a.projectKeyOrId)}`),
    },
    {
      name: "jira_list_issue_types",
      description: "List issue types for a project.",
      inputSchema: {
        type: "object",
        properties: {
          projectKeyOrId: { type: "string" },
        },
        required: ["projectKeyOrId"],
      },
      handler: async (a) => {
        const project = (await client.jiraGet(`/rest/api/2/project/${enc(a.projectKeyOrId)}`)) as {
          id?: string;
          issueTypes?: unknown[];
        };
        return { issueTypes: project.issueTypes ?? [] };
      },
    },
    {
      name: "jira_list_priorities",
      description: "List all available priorities in the Jira instance.",
      inputSchema: { type: "object", properties: {} },
      handler: async () => client.jiraGet("/rest/api/2/priority"),
    },
    {
      name: "jira_list_statuses",
      description: "List all statuses, or statuses for one project if projectKeyOrId is set.",
      inputSchema: {
        type: "object",
        properties: { projectKeyOrId: { type: "string" } },
      },
      handler: async (a) =>
        a.projectKeyOrId
          ? client.jiraGet(`/rest/api/2/project/${enc(a.projectKeyOrId)}/statuses`)
          : client.jiraGet("/rest/api/2/status"),
    },
    {
      name: "jira_search_users",
      description: "Find Jira users by query (name, email). Returns accountId / name for assignee fields.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string" },
          maxResults: { type: "number" },
        },
        required: ["query"],
      },
      handler: async (a) =>
        client.jiraGet("/rest/api/2/user/search", {
          query: a.query,
          maxResults: a.maxResults ?? 20,
        }),
    },

    // ─── issues: read ─────────────────────────────────────────────────
    {
      name: "jira_search_issues",
      description:
        "Search issues with JQL (cursor-paginated). Examples: 'project = DEV AND status = Open', 'assignee = currentUser() ORDER BY updated DESC'.",
      inputSchema: {
        type: "object",
        properties: {
          jql: { type: "string", description: "JQL query string" },
          fields: {
            type: "array",
            items: { type: "string" },
            description: "Fields to return (default summary,status,assignee,updated,priority)",
          },
          maxResults: { type: "number", description: "Default 50, max 100" },
          startAt: { type: "number", description: "Pagination offset" },
        },
        required: ["jql"],
      },
      handler: async (a) =>
        client.jiraPost("/rest/api/2/search", {
          jql: a.jql,
          fields: a.fields ?? ["summary", "status", "assignee", "updated", "priority"],
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_get_issue",
      description: "Fetch a single issue by key or numeric id.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string", description: "Issue key like DEV-123 or numeric id" },
          fields: { type: "array", items: { type: "string" } },
          expand: { type: "string" },
        },
        required: ["issueKey"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/issue/${enc(a.issueKey)}`, {
          fields: a.fields ? a.fields.join(",") : undefined,
          expand: a.expand,
        }),
    },
    {
      name: "jira_get_transitions",
      description: "Get available workflow transitions for an issue.",
      inputSchema: {
        type: "object",
        properties: { issueKey: { type: "string" } },
        required: ["issueKey"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/issue/${enc(a.issueKey)}/transitions`),
    },
    {
      name: "jira_list_comments",
      description: "List comments on an issue.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
        },
        required: ["issueKey"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/issue/${enc(a.issueKey)}/comment`, {
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_list_attachments",
      description: "List attachments on an issue.",
      inputSchema: {
        type: "object",
        properties: { issueKey: { type: "string" } },
        required: ["issueKey"],
      },
      handler: async (a) => {
        const issue = (await client.jiraGet(`/rest/api/2/issue/${enc(a.issueKey)}`, {
          fields: "attachment",
        })) as { fields?: { attachment?: unknown[] } };
        return { attachments: issue.fields?.attachment ?? [] };
      },
    },
    {
      name: "jira_list_link_types",
      description: "List all available issue link types.",
      inputSchema: { type: "object", properties: {} },
      handler: async () => client.jiraGet("/rest/api/2/issueLinkType"),
    },
    {
      name: "jira_list_worklogs",
      description: "List worklogs on an issue.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
        },
        required: ["issueKey"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/issue/${enc(a.issueKey)}/worklog`, {
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_list_versions",
      description: "List fix versions for a project.",
      inputSchema: {
        type: "object",
        properties: { projectKeyOrId: { type: "string" } },
        required: ["projectKeyOrId"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/project/${enc(a.projectKeyOrId)}/versions`),
    },
    {
      name: "jira_list_components",
      description: "List components for a project.",
      inputSchema: {
        type: "object",
        properties: { projectKeyOrId: { type: "string" } },
        required: ["projectKeyOrId"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/api/2/project/${enc(a.projectKeyOrId)}/components`),
    },
    {
      name: "jira_list_boards",
      description: "List Scrum/Kanban boards. Optional: projectKeyOrId to filter.",
      inputSchema: {
        type: "object",
        properties: {
          projectKeyOrId: { type: "string" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
        },
      },
      handler: async (a) =>
        client.jiraGet("/rest/agile/1.0/board", {
          projectKeyOrId: a.projectKeyOrId,
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_get_board_backlog",
      description: "Get issues in a board's backlog.",
      inputSchema: {
        type: "object",
        properties: {
          boardId: { type: "number" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
          jql: { type: "string" },
        },
        required: ["boardId"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/agile/1.0/board/${a.boardId}/backlog`, {
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
          jql: a.jql,
        }),
    },
    {
      name: "jira_list_sprints",
      description: "List sprints for a board.",
      inputSchema: {
        type: "object",
        properties: {
          boardId: { type: "number" },
          state: { type: "string", description: "active | closed | future" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
        },
        required: ["boardId"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/agile/1.0/board/${a.boardId}/sprint`, {
          state: a.state,
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
        }),
    },
    {
      name: "jira_get_sprint_issues",
      description: "Get issues in a sprint.",
      inputSchema: {
        type: "object",
        properties: {
          sprintId: { type: "number" },
          maxResults: { type: "number" },
          startAt: { type: "number" },
          jql: { type: "string" },
        },
        required: ["sprintId"],
      },
      handler: async (a) =>
        client.jiraGet(`/rest/agile/1.0/sprint/${a.sprintId}/issue`, {
          maxResults: a.maxResults ?? 50,
          startAt: a.startAt ?? 0,
          jql: a.jql,
        }),
    },

    // ─── issues: write ────────────────────────────────────────────────
    {
      name: "jira_create_issue",
      description:
        "Create an issue. Required: projectKey, summary, issueTypeName. Optional: description, assigneeUsername, labels, priorityName, parentKey.",
      inputSchema: {
        type: "object",
        properties: {
          projectKey: { type: "string" },
          summary: { type: "string" },
          issueTypeName: { type: "string", description: "e.g. Task, Bug, Story, Epic, Sub-task" },
          description: { type: "string" },
          assigneeUsername: { type: "string" },
          labels: { type: "array", items: { type: "string" } },
          priorityName: { type: "string" },
          parentKey: { type: "string", description: "Parent issue key for sub-tasks" },
        },
        required: ["projectKey", "summary", "issueTypeName"],
      },
      handler: async (a) => {
        const fields: Record<string, unknown> = {
          project: { key: a.projectKey },
          summary: a.summary,
          issuetype: { name: a.issueTypeName },
        };
        if (a.description) fields.description = plainBody(a.description);
        if (a.assigneeUsername) fields.assignee = { name: a.assigneeUsername };
        if (a.labels) fields.labels = a.labels;
        if (a.priorityName) fields.priority = { name: a.priorityName };
        if (a.parentKey) fields.parent = { key: a.parentKey };
        return client.jiraPost("/rest/api/2/issue", { fields });
      },
    },
    {
      name: "jira_update_issue",
      description: "Update an issue. Pass any of: summary, description, assigneeUsername, labels, priorityName.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          summary: { type: "string" },
          description: { type: "string" },
          assigneeUsername: { type: "string" },
          labels: { type: "array", items: { type: "string" } },
          priorityName: { type: "string" },
        },
        required: ["issueKey"],
      },
      handler: async (a) => {
        const fields: Record<string, unknown> = {};
        if (a.summary) fields.summary = a.summary;
        if (a.description) fields.description = plainBody(a.description);
        if (a.assigneeUsername) fields.assignee = { name: a.assigneeUsername };
        if (a.labels) fields.labels = a.labels;
        if (a.priorityName) fields.priority = { name: a.priorityName };
        await client.jiraPut(`/rest/api/2/issue/${enc(a.issueKey)}`, { fields });
        return { ok: true, updated: a.issueKey };
      },
    },
    {
      name: "jira_transition_issue",
      description: "Transition an issue to a new status. Use jira_get_transitions first to get transitionId.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          transitionId: { type: "string" },
          comment: { type: "string" },
        },
        required: ["issueKey", "transitionId"],
      },
      handler: async (a) => {
        const body: Record<string, unknown> = { transition: { id: a.transitionId } };
        if (a.comment) {
          body.update = { comment: [{ add: { body: a.comment } }] };
        }
        await client.jiraPost(`/rest/api/2/issue/${enc(a.issueKey)}/transitions`, body);
        return { ok: true, transitioned: a.issueKey };
      },
    },
    {
      name: "jira_delete_issue",
      description: "Delete an issue. DESTRUCTIVE.",
      inputSchema: {
        type: "object",
        properties: { issueKey: { type: "string" } },
        required: ["issueKey"],
      },
      handler: async (a) => {
        await client.jiraDelete(`/rest/api/2/issue/${enc(a.issueKey)}`);
        return { ok: true, deleted: a.issueKey };
      },
    },
    {
      name: "jira_add_comment",
      description: "Add a comment to an issue.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          body: { type: "string" },
        },
        required: ["issueKey", "body"],
      },
      handler: async (a) =>
        client.jiraPost(`/rest/api/2/issue/${enc(a.issueKey)}/comment`, {
          body: a.body,
        }),
    },
    {
      name: "jira_update_comment",
      description: "Update an existing comment.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          commentId: { type: "string" },
          body: { type: "string" },
        },
        required: ["issueKey", "commentId", "body"],
      },
      handler: async (a) =>
        client.jiraPut(`/rest/api/2/issue/${enc(a.issueKey)}/comment/${enc(a.commentId)}`, {
          body: a.body,
        }),
    },
    {
      name: "jira_add_worklog",
      description: "Log time on an issue. timeSpent format: '1h 30m', '2d', etc.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          timeSpent: { type: "string" },
          comment: { type: "string" },
          started: { type: "string", description: "ISO 8601 datetime (default: now)" },
        },
        required: ["issueKey", "timeSpent"],
      },
      handler: async (a) =>
        client.jiraPost(`/rest/api/2/issue/${enc(a.issueKey)}/worklog`, {
          timeSpent: a.timeSpent,
          comment: a.comment,
          started: a.started,
        }),
    },
    {
      name: "jira_link_issues",
      description: "Link two issues. Use jira_list_link_types to find available link type names.",
      inputSchema: {
        type: "object",
        properties: {
          inwardIssueKey: { type: "string" },
          outwardIssueKey: { type: "string" },
          linkTypeName: { type: "string", description: "e.g. Blocks, Relates, Clones" },
          comment: { type: "string" },
        },
        required: ["inwardIssueKey", "outwardIssueKey", "linkTypeName"],
      },
      handler: async (a) => {
        const body: Record<string, unknown> = {
          type: { name: a.linkTypeName },
          inwardIssue: { key: a.inwardIssueKey },
          outwardIssue: { key: a.outwardIssueKey },
        };
        if (a.comment) body.comment = { body: a.comment };
        return client.jiraPost("/rest/api/2/issueLink", body);
      },
    },
    {
      name: "jira_assign_issue",
      description: "Assign an issue to a user by username. Pass null to unassign.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          assigneeUsername: { type: "string", description: "Username or null to unassign" },
        },
        required: ["issueKey"],
      },
      handler: async (a) => {
        await client.jiraPut(`/rest/api/2/issue/${enc(a.issueKey)}/assignee`, {
          name: a.assigneeUsername ?? null,
        });
        return { ok: true, assigned: a.issueKey };
      },
    },
    {
      name: "jira_upload_attachment",
      description: "Upload a local file as an attachment to an issue. DEVSTACK_FILE_ROOT must be set.",
      inputSchema: {
        type: "object",
        properties: {
          issueKey: { type: "string" },
          filePath: { type: "string" },
        },
        required: ["issueKey", "filePath"],
      },
      handler: async (a) => client.uploadJiraAttachment(a.issueKey, a.filePath),
    },
  ];
}
