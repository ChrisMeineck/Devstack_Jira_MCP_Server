import { constants } from "node:fs";
import { access, readFile, writeFile, stat } from "node:fs/promises";
import { basename, isAbsolute, relative, resolve } from "node:path";

export type DevstackConfig = {
  jiraBaseUrl: string;
  confluenceBaseUrl: string;
  username: string;
  /** Personal Access Token or password */
  token: string;
};

export type FileAccessConfig = {
  fileRoot?: string;
};

const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

export class DevstackError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(`Devstack API ${status}: ${message}`);
    this.name = "DevstackError";
  }
}

export class DevstackClient {
  private jiraBaseUrl: string;
  private confluenceBaseUrl: string;
  private authHeader: string;
  private fileRoot?: string;

  constructor(cfg: DevstackConfig, fileAccess: FileAccessConfig = {}) {
    this.jiraBaseUrl = cfg.jiraBaseUrl.replace(/\/+$/, "");
    this.confluenceBaseUrl = cfg.confluenceBaseUrl.replace(/\/+$/, "");
    const basic = Buffer.from(`${cfg.username}:${cfg.token}`, "utf8").toString("base64");
    this.authHeader = `Basic ${basic}`;
    this.fileRoot = fileAccess.fileRoot ? resolve(fileAccess.fileRoot) : undefined;
  }

  private buildUrl(
    service: "jira" | "confluence",
    path: string,
    query?: Record<string, string | number | boolean | undefined>,
  ): string {
    const isAbsoluteUrl = /^https?:\/\//.test(path);
    const baseUrl = service === "jira" ? this.jiraBaseUrl : this.confluenceBaseUrl;
    const url = new URL(isAbsoluteUrl ? path : baseUrl + path);

    const allowedBase = new URL(baseUrl);
    if (url.origin !== allowedBase.origin) {
      throw new Error(
        `Refusing to send credentials to a different origin (${url.origin} vs ${allowedBase.origin})`,
      );
    }

    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
      }
    }
    return url.toString();
  }

  private resolveSafeFilePath(filePath: string): string {
    if (!this.fileRoot) {
      throw new Error(
        "Attachment file access is disabled. Set DEVSTACK_FILE_ROOT to an allowed directory.",
      );
    }
    const resolved = isAbsolute(filePath) ? resolve(filePath) : resolve(this.fileRoot, filePath);
    const rel = relative(this.fileRoot, resolved);
    if (rel === "" || rel.startsWith("..") || isAbsolute(rel)) {
      throw new Error(`Refusing file path outside DEVSTACK_FILE_ROOT: ${filePath}`);
    }
    return resolved;
  }

  private assertFileSize(bytes: number): void {
    if (bytes > MAX_ATTACHMENT_BYTES) {
      throw new Error(`File is too large (${bytes} bytes). Limit is ${MAX_ATTACHMENT_BYTES} bytes.`);
    }
  }

  async request<T = unknown>(
    service: "jira" | "confluence",
    method: string,
    path: string,
    opts: { query?: Record<string, string | number | boolean | undefined>; body?: unknown } = {},
  ): Promise<T> {
    const res = await fetch(this.buildUrl(service, path, opts.query), {
      method,
      headers: {
        Authorization: this.authHeader,
        Accept: "application/json",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });

    const text = await res.text();
    let data: unknown = text;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        // not JSON — keep as text
      }
    }

    if (!res.ok) throw new DevstackError(res.statusText, res.status, data);
    return data as T;
  }

  jiraGet<T = unknown>(path: string, query?: Record<string, string | number | boolean | undefined>) {
    return this.request<T>("jira", "GET", path, { query });
  }
  jiraPost<T = unknown>(path: string, body?: unknown) {
    return this.request<T>("jira", "POST", path, { body });
  }
  jiraPut<T = unknown>(path: string, body?: unknown) {
    return this.request<T>("jira", "PUT", path, { body });
  }
  jiraDelete<T = unknown>(path: string, query?: Record<string, string | number | boolean | undefined>) {
    return this.request<T>("jira", "DELETE", path, { query });
  }

  confluenceGet<T = unknown>(path: string, query?: Record<string, string | number | boolean | undefined>) {
    return this.request<T>("confluence", "GET", path, { query });
  }
  confluencePost<T = unknown>(path: string, body?: unknown) {
    return this.request<T>("confluence", "POST", path, { body });
  }
  confluencePut<T = unknown>(path: string, body?: unknown) {
    return this.request<T>("confluence", "PUT", path, { body });
  }
  confluenceDelete<T = unknown>(path: string) {
    return this.request<T>("confluence", "DELETE", path);
  }

  async uploadJiraAttachment<T = unknown>(issueKey: string, filePath: string): Promise<T> {
    const safeFilePath = this.resolveSafeFilePath(filePath);
    const stats = await stat(safeFilePath);
    if (!stats.isFile()) throw new Error(`Not a file: ${filePath}`);
    this.assertFileSize(stats.size);
    const buf = await readFile(safeFilePath);
    const filename = basename(safeFilePath);

    const form = new FormData();
    form.append("file", new Blob([buf]), filename);

    const url = this.buildUrl("jira", `/rest/api/2/issue/${encodeURIComponent(issueKey)}/attachments`);
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: this.authHeader,
        Accept: "application/json",
        "X-Atlassian-Token": "no-check",
      },
      body: form,
    });

    const text = await res.text();
    let data: unknown = text;
    try { data = JSON.parse(text); } catch { /* keep as text */ }
    if (!res.ok) throw new DevstackError(res.statusText, res.status, data);
    return data as T;
  }

  async uploadConfluenceAttachment<T = unknown>(
    pageId: string,
    filePath: string,
    opts: { comment?: string } = {},
  ): Promise<T> {
    const safeFilePath = this.resolveSafeFilePath(filePath);
    const stats = await stat(safeFilePath);
    if (!stats.isFile()) throw new Error(`Not a file: ${filePath}`);
    this.assertFileSize(stats.size);
    const buf = await readFile(safeFilePath);
    const filename = basename(safeFilePath);

    const form = new FormData();
    form.append("file", new Blob([buf]), filename);
    if (opts.comment) form.append("comment", opts.comment);
    form.append("minorEdit", "true");

    const url = this.buildUrl(
      "confluence",
      `/rest/api/content/${encodeURIComponent(pageId)}/child/attachment`,
    );
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: this.authHeader,
        Accept: "application/json",
        "X-Atlassian-Token": "no-check",
      },
      body: form,
    });

    const text = await res.text();
    let data: unknown = text;
    try { data = JSON.parse(text); } catch { /* keep as text */ }
    if (!res.ok) throw new DevstackError(res.statusText, res.status, data);
    return data as T;
  }

  async downloadBinary(
    service: "jira" | "confluence",
    pathOrUrl: string,
    opts: { outputPath?: string } = {},
  ): Promise<{ status: number; bytes: number; contentType: string; outputPath?: string; base64?: string }> {
    const res = await fetch(this.buildUrl(service, pathOrUrl), {
      method: "GET",
      headers: { Authorization: this.authHeader },
      redirect: "follow",
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new DevstackError(res.statusText, res.status, errText);
    }

    const contentType = res.headers.get("content-type") ?? "application/octet-stream";
    const contentLength = res.headers.get("content-length");
    if (contentLength && /^\d+$/.test(contentLength)) this.assertFileSize(Number(contentLength));

    const buf = Buffer.from(await res.arrayBuffer());
    this.assertFileSize(buf.byteLength);

    if (opts.outputPath) {
      const outputPath = this.resolveSafeFilePath(opts.outputPath);
      try {
        await access(outputPath, constants.F_OK);
        throw new Error(`Refusing to overwrite existing file: ${outputPath}`);
      } catch (err) {
        if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
      }
      await writeFile(outputPath, buf, { flag: "wx" });
      return { status: res.status, bytes: buf.byteLength, contentType, outputPath };
    }
    return { status: res.status, bytes: buf.byteLength, contentType, base64: buf.toString("base64") };
  }
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): DevstackConfig {
  const jiraBaseUrl = env.DEVSTACK_JIRA_BASE_URL;
  const confluenceBaseUrl = env.DEVSTACK_CONFLUENCE_BASE_URL;
  const username = env.DEVSTACK_USERNAME;
  const token = env.DEVSTACK_TOKEN;

  if (!jiraBaseUrl || !confluenceBaseUrl || !username || !token) {
    throw new Error(
      "Missing environment variables. Required:\n" +
        "  DEVSTACK_JIRA_BASE_URL        e.g. https://jira.example.com\n" +
        "  DEVSTACK_CONFLUENCE_BASE_URL  e.g. https://confluence.example.com\n" +
        "  DEVSTACK_USERNAME             your Devstack username\n" +
        "  DEVSTACK_TOKEN                your Personal Access Token or password",
    );
  }

  const parsedJira = new URL(jiraBaseUrl);
  if (parsedJira.protocol !== "https:") throw new Error("DEVSTACK_JIRA_BASE_URL must use https");

  const parsedConf = new URL(confluenceBaseUrl);
  if (parsedConf.protocol !== "https:") throw new Error("DEVSTACK_CONFLUENCE_BASE_URL must use https");

  return {
    jiraBaseUrl: parsedJira.origin,
    confluenceBaseUrl: parsedConf.origin,
    username,
    token,
  };
}
