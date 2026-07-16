import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

export type HumanitecDevicePolicy = {
  allowed_roots: string[];
  exec_whitelist: string[];
  exec_require_confirm: boolean;
  shell_enabled: boolean;
  browser_enabled: boolean;
  max_file_size_mb: number;
};

type McpToolDefinition = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
};

function asPolicy(policy: Record<string, unknown> | null): HumanitecDevicePolicy {
  if (policy === null) {
    return {
      allowed_roots: [],
      exec_whitelist: [],
      exec_require_confirm: true,
      shell_enabled: false,
      browser_enabled: false,
      max_file_size_mb: 50,
    };
  }
  const allowedRoots = policy.allowed_roots;
  const execWhitelist = policy.exec_whitelist;
  return {
    allowed_roots: Array.isArray(allowedRoots)
      ? allowedRoots.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
      : [],
    exec_whitelist: Array.isArray(execWhitelist)
      ? execWhitelist.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
      : [],
    exec_require_confirm: policy.exec_require_confirm === true,
    shell_enabled: policy.shell_enabled === true,
    browser_enabled: policy.browser_enabled === true,
    max_file_size_mb:
      typeof policy.max_file_size_mb === 'number' && policy.max_file_size_mb >= 1
        ? policy.max_file_size_mb
        : 50,
  };
}

function listTools(policy: HumanitecDevicePolicy): McpToolDefinition[] {
  const tools: McpToolDefinition[] = [];
  if (policy.allowed_roots.length > 0) {
    tools.push(
      {
        name: 'device_list_dir',
        description: 'List entries in a directory under DevicePolicy allowed_roots',
        inputSchema: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'Absolute directory path' },
          },
          required: ['path'],
        },
      },
      {
        name: 'device_read_file',
        description: 'Read a UTF-8 text file under DevicePolicy allowed_roots',
        inputSchema: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'Absolute file path' },
          },
          required: ['path'],
        },
      },
      {
        name: 'device_write_file',
        description: 'Write UTF-8 text to a file under DevicePolicy allowed_roots',
        inputSchema: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'Absolute file path' },
            content: { type: 'string', description: 'File contents' },
          },
          required: ['path', 'content'],
        },
      },
    );
  }
  if (policy.shell_enabled) {
    tools.push({
      name: 'device_shell_exec',
      description:
        'Execute a whitelisted shell command (DevicePolicy.exec_whitelist). Denied if whitelist empty or confirm required.',
      inputSchema: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'Executable name from whitelist' },
          args: {
            type: 'array',
            items: { type: 'string' },
            description: 'Command arguments',
          },
          cwd: { type: 'string', description: 'Optional working directory under allowed_roots' },
        },
        required: ['command'],
      },
    });
  }
  if (policy.browser_enabled) {
    tools.push({
      name: 'device_open_url',
      description: 'Open an http(s) URL with the system default browser',
      inputSchema: {
        type: 'object',
        properties: {
          url: { type: 'string', description: 'http or https URL' },
        },
        required: ['url'],
      },
    });
  }
  return tools;
}

async function resolveAllowedPath(
  policy: HumanitecDevicePolicy,
  rawPath: string,
): Promise<string> {
  if (typeof rawPath !== 'string' || !rawPath.trim()) {
    throw new Error('path is required');
  }
  if (policy.allowed_roots.length === 0) {
    throw new Error('DevicePolicy.allowed_roots is empty');
  }
  const resolved = path.resolve(rawPath.trim());
  const realTarget = await fs.realpath(resolved).catch(async () => {
    const parent = path.dirname(resolved);
    const realParent = await fs.realpath(parent);
    return path.join(realParent, path.basename(resolved));
  });
  for (const root of policy.allowed_roots) {
    const realRoot = await fs.realpath(path.resolve(root));
    if (realTarget === realRoot || realTarget.startsWith(`${realRoot}${path.sep}`)) {
      return realTarget;
    }
  }
  throw new Error(`path is outside DevicePolicy.allowed_roots: ${resolved}`);
}

async function callTool(
  policy: HumanitecDevicePolicy,
  name: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  switch (name) {
    case 'device_list_dir': {
      const dirPath = await resolveAllowedPath(policy, String(args.path ?? ''));
      const entries = await fs.readdir(dirPath, { withFileTypes: true });
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              entries.map((entry) => ({
                name: entry.name,
                type: entry.isDirectory() ? 'directory' : 'file',
              })),
              null,
              2,
            ),
          },
        ],
      };
    }
    case 'device_read_file': {
      const filePath = await resolveAllowedPath(policy, String(args.path ?? ''));
      const stat = await fs.stat(filePath);
      const maxBytes = policy.max_file_size_mb * 1024 * 1024;
      if (stat.size > maxBytes) {
        throw new Error(`file exceeds max_file_size_mb=${policy.max_file_size_mb}`);
      }
      const content = await fs.readFile(filePath, 'utf8');
      return { content: [{ type: 'text', text: content }] };
    }
    case 'device_write_file': {
      const filePath = await resolveAllowedPath(policy, String(args.path ?? ''));
      const content = args.content;
      if (typeof content !== 'string') {
        throw new Error('content must be a string');
      }
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      await fs.writeFile(filePath, content, 'utf8');
      return { content: [{ type: 'text', text: `wrote ${filePath}` }] };
    }
    case 'device_shell_exec': {
      if (!policy.shell_enabled) {
        throw new Error('DevicePolicy.shell_enabled is false');
      }
      if (policy.exec_require_confirm) {
        throw new Error(
          'DevicePolicy.exec_require_confirm is true; disable confirm in Settings to allow shell via tunnel',
        );
      }
      if (policy.exec_whitelist.length === 0) {
        throw new Error('DevicePolicy.exec_whitelist is empty');
      }
      const command = args.command;
      if (typeof command !== 'string' || !command.trim()) {
        throw new Error('command is required');
      }
      const commandName = path.basename(command.trim());
      if (!policy.exec_whitelist.includes(commandName) && !policy.exec_whitelist.includes(command.trim())) {
        throw new Error(`command not in exec_whitelist: ${commandName}`);
      }
      const rawArgs = args.args;
      const argv = Array.isArray(rawArgs)
        ? rawArgs.filter((item): item is string => typeof item === 'string')
        : [];
      let cwd: string | undefined;
      if (typeof args.cwd === 'string' && args.cwd.trim()) {
        cwd = await resolveAllowedPath(policy, args.cwd);
      }
      const { stdout, stderr } = await execFileAsync(command.trim(), argv, {
        cwd,
        timeout: 60_000,
        maxBuffer: 2 * 1024 * 1024,
      });
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({ stdout, stderr }, null, 2),
          },
        ],
      };
    }
    case 'device_open_url': {
      if (!policy.browser_enabled) {
        throw new Error('DevicePolicy.browser_enabled is false');
      }
      const url = args.url;
      if (typeof url !== 'string' || !url.trim()) {
        throw new Error('url is required');
      }
      const trimmed = url.trim();
      if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
        throw new Error('url must start with http:// or https://');
      }
      const platform = process.platform;
      if (platform === 'darwin') {
        await execFileAsync('open', [trimmed]);
      } else if (platform === 'win32') {
        await execFileAsync('cmd', ['/c', 'start', '', trimmed]);
      } else {
        await execFileAsync('xdg-open', [trimmed]);
      }
      return { content: [{ type: 'text', text: `opened ${trimmed}` }] };
    }
    default:
      throw new Error(`Unknown local device tool: ${name}`);
  }
}

export async function handleBuiltInLocalDeviceMcp(
  method: string,
  params: Record<string, unknown>,
  policyRaw: Record<string, unknown> | null,
): Promise<Record<string, unknown>> {
  const policy = asPolicy(policyRaw);
  if (method === 'tools/list') {
    return { tools: listTools(policy) };
  }
  if (method === 'tools/call') {
    const name = params.name;
    if (typeof name !== 'string' || !name.trim()) {
      throw new Error('tools/call requires params.name');
    }
    const argumentsRaw = params.arguments;
    const callArgs =
      typeof argumentsRaw === 'object' && argumentsRaw !== null && !Array.isArray(argumentsRaw)
        ? (argumentsRaw as Record<string, unknown>)
        : {};
    return callTool(policy, name.trim(), callArgs);
  }
  throw new Error(`Unsupported local device MCP method: ${method}`);
}
