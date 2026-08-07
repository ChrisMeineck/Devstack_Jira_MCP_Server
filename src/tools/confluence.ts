import type { DevstackClient } from "../devstack-client.js";
import type { ToolDef } from "./types.js";

const enc = encodeURIComponent;

export function buildConfluenceTools(client: DevstackClient): ToolDef[] {
  return [
    // ─── spaces ───────────────────────────────────────────────────────
    {
      name: "confluence_list_spaces",
      description: "List Confluence spaces. Paginated.",
      inputSchema: {
        type: "object",
        properties: {
          limit: { type: "number", description: "Max results (default 25, max 100)" },
          start: { type: "number", description: "Pagination offset" },
          type: { type: "string", description: "global | personal" },
          status: { type: "string", description: "current | archived" },
        },
      },
      handler: async (a) =>
        client.confluenceGet("/rest/api/space", {
          limit: a.limit ?? 25,
          start: a.start ?? 0,
          type: a.type,
          status: a.status,
        }),
    },
    {
      name: "confluence_get_space",
      description: "Fetch one space by key.",
      inputSchema: {
        type: "object",
        properties: { spaceKey: { type: "string" } },
        required: ["spaceKey"],
      },
      handler: async (a) => client.confluenceGet(`/rest/api/space/${enc(a.spaceKey)}`),
    },

    // ─── search ───────────────────────────────────────────────────────
    {
      name: "confluence_search",
      description:
        "Search Confluence with CQL. Examples: 'type=page AND space=DOCS', 'text ~ \"onboarding\" AND lastModified > now(\"-7d\")'.",
      inputSchema: {
        type: "object",
        properties: {
          cql: { type: "string", description: "CQL query" },
          limit: { type: "number", description: "Default 25" },
          start: { type: "number", description: "Pagination offset" },
          expand: { type: "string", description: "Expand options, comma-separated" },
        },
        required: ["cql"],
      },
      handler: async (a) =>
        client.confluenceGet("/rest/api/search", {
          cql: a.cql,
          limit: a.limit ?? 25,
          start: a.start ?? 0,
          expand: a.expand,
        }),
    },
    {
      name: "confluence_search_content",
      description: "Search Confluence content by title, space, type, or full-text query.",
      inputSchema: {
        type: "object",
        properties: {
          title: { type: "string" },
          spaceKey: { type: "string" },
          type: { type: "string", description: "page | blogpost | comment | attachment" },
          status: { type: "string", description: "current | draft | archived" },
          limit: { type: "number" },
          start: { type: "number" },
          expand: { type: "string" },
        },
      },
      handler: async (a) =>
        client.confluenceGet("/rest/api/content", {
          title: a.title,
          spaceKey: a.spaceKey,
          type: a.type,
          status: a.status ?? "current",
          limit: a.limit ?? 25,
          start: a.start ?? 0,
          expand: a.expand,
        }),
    },

    // ─── pages: read ──────────────────────────────────────────────────
    {
      name: "confluence_get_page",
      description: "Fetch a Confluence page by id. Use expand='body.storage' to include the body.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          expand: {
            type: "string",
            description: "e.g. 'body.storage,version,ancestors' (default body.storage,version)",
          },
        },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}`, {
          expand: a.expand ?? "body.storage,version",
        }),
    },
    {
      name: "confluence_get_page_children",
      description: "List direct child pages of a page.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          limit: { type: "number" },
          start: { type: "number" },
        },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}/child/page`, {
          limit: a.limit ?? 25,
          start: a.start ?? 0,
        }),
    },
    {
      name: "confluence_get_page_ancestors",
      description: "Get the ancestor chain of a page (root → parent).",
      inputSchema: {
        type: "object",
        properties: { pageId: { type: "string" } },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}`, {
          expand: "ancestors",
        }),
    },
    {
      name: "confluence_list_page_versions",
      description: "List historical versions of a page.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          limit: { type: "number" },
          start: { type: "number" },
        },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}/history`, {
          limit: a.limit ?? 25,
          start: a.start ?? 0,
        }),
    },

    // ─── pages: write ─────────────────────────────────────────────────
    {
      name: "confluence_create_page",
      description:
        "Create a Confluence page. Body uses Confluence 'storage' format (HTML-like XHTML). Wrap plain text in <p>...</p>.",
      inputSchema: {
        type: "object",
        properties: {
          spaceKey: { type: "string" },
          title: { type: "string" },
          bodyStorage: { type: "string", description: "Body in storage (XHTML) format" },
          parentId: { type: "string", description: "Optional parent page id" },
          status: { type: "string", description: "current | draft (default current)" },
        },
        required: ["spaceKey", "title", "bodyStorage"],
      },
      handler: async (a) => {
        const body: Record<string, unknown> = {
          type: "page",
          title: a.title,
          status: a.status ?? "current",
          space: { key: a.spaceKey },
          body: {
            storage: {
              value: a.bodyStorage,
              representation: "storage",
            },
          },
        };
        if (a.parentId) body.ancestors = [{ id: a.parentId }];
        return client.confluencePost("/rest/api/content", body);
      },
    },
    {
      name: "confluence_update_page",
      description:
        "Update a Confluence page. versionNumber MUST be current version + 1. Use confluence_get_page first to read the current version.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          title: { type: "string" },
          bodyStorage: { type: "string" },
          versionNumber: { type: "number", description: "Current version + 1" },
        },
        required: ["pageId", "title", "bodyStorage", "versionNumber"],
      },
      handler: async (a) =>
        client.confluencePut(`/rest/api/content/${enc(a.pageId)}`, {
          type: "page",
          title: a.title,
          version: { number: a.versionNumber },
          body: {
            storage: {
              value: a.bodyStorage,
              representation: "storage",
            },
          },
        }),
    },
    {
      name: "confluence_delete_page",
      description: "Delete a Confluence page. DESTRUCTIVE.",
      inputSchema: {
        type: "object",
        properties: { pageId: { type: "string" } },
        required: ["pageId"],
      },
      handler: async (a) => {
        await client.confluenceDelete(`/rest/api/content/${enc(a.pageId)}`);
        return { ok: true, deleted: a.pageId };
      },
    },

    // ─── comments ─────────────────────────────────────────────────────
    {
      name: "confluence_list_comments",
      description: "List comments on a page.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          limit: { type: "number" },
          start: { type: "number" },
        },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}/child/comment`, {
          limit: a.limit ?? 25,
          start: a.start ?? 0,
          expand: "body.storage",
        }),
    },
    {
      name: "confluence_add_comment",
      description: "Add a comment to a page. bodyStorage uses Confluence storage format.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          bodyStorage: { type: "string" },
        },
        required: ["pageId", "bodyStorage"],
      },
      handler: async (a) =>
        client.confluencePost("/rest/api/content", {
          type: "comment",
          container: { id: a.pageId, type: "page" },
          body: {
            storage: {
              value: a.bodyStorage,
              representation: "storage",
            },
          },
        }),
    },

    // ─── labels ───────────────────────────────────────────────────────
    {
      name: "confluence_get_page_labels",
      description: "List labels on a page.",
      inputSchema: {
        type: "object",
        properties: { pageId: { type: "string" } },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}/label`),
    },
    {
      name: "confluence_add_page_labels",
      description: "Add labels to a page.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          labels: { type: "array", items: { type: "string" } },
        },
        required: ["pageId", "labels"],
      },
      handler: async (a) =>
        client.confluencePost(
          `/rest/api/content/${enc(a.pageId)}/label`,
          a.labels.map((name: string) => ({ prefix: "global", name })),
        ),
    },

    // ─── attachments ──────────────────────────────────────────────────
    {
      name: "confluence_list_page_attachments",
      description: "List attachments on a page.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          limit: { type: "number" },
          start: { type: "number" },
        },
        required: ["pageId"],
      },
      handler: async (a) =>
        client.confluenceGet(`/rest/api/content/${enc(a.pageId)}/child/attachment`, {
          limit: a.limit ?? 25,
          start: a.start ?? 0,
        }),
    },
    {
      name: "confluence_upload_attachment",
      description:
        "Upload a local file as an attachment to a Confluence page. DEVSTACK_FILE_ROOT must be set.",
      inputSchema: {
        type: "object",
        properties: {
          pageId: { type: "string" },
          filePath: { type: "string" },
          comment: { type: "string" },
        },
        required: ["pageId", "filePath"],
      },
      handler: async (a) =>
        client.uploadConfluenceAttachment(a.pageId, a.filePath, { comment: a.comment }),
    },

    // ─── blogposts ────────────────────────────────────────────────────
    {
      name: "confluence_create_blogpost",
      description: "Create a blog post in a space.",
      inputSchema: {
        type: "object",
        properties: {
          spaceKey: { type: "string" },
          title: { type: "string" },
          bodyStorage: { type: "string", description: "Body in storage (XHTML) format" },
          status: { type: "string", description: "current | draft (default current)" },
        },
        required: ["spaceKey", "title", "bodyStorage"],
      },
      handler: async (a) =>
        client.confluencePost("/rest/api/content", {
          type: "blogpost",
          title: a.title,
          status: a.status ?? "current",
          space: { key: a.spaceKey },
          body: {
            storage: {
              value: a.bodyStorage,
              representation: "storage",
            },
          },
        }),
    },
  ];
}
