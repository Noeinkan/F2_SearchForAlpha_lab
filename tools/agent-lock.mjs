#!/usr/bin/env node
/**
 * Cooperative file semaphore for parallel Cursor agents.
 * Acquire is all-or-nothing, paths sorted, registry mutated under an exclusive mutex.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOCK_DIR = path.join(ROOT, ".cursor", "locks");
const REGISTRY_PATH = path.join(LOCK_DIR, "registry.json");
const MUTEX_PATH = path.join(LOCK_DIR, ".mutex");

const DEFAULT_TTL_MS = 5 * 60 * 1000;
const POLL_MS = 2000;
const WAIT_LOG_MS = 10_000;
const MUTEX_STALE_MS = 10_000;

function usage(exit = 1) {
  console.error(`Usage:
  node tools/agent-lock.mjs acquire --holder <id> [--wait] [--any] [--timeout 0] [--force] -- <paths...>
  node tools/agent-lock.mjs release --holder <id> [-- <paths...>]
  node tools/agent-lock.mjs heartbeat --holder <id>
  node tools/agent-lock.mjs status

--wait polls until success. --timeout 0 (default with --wait) means forever.
--any takes every path that is free now; with --wait, blocks until at least one is free.
Paths may be files or directories. A directory lock covers everything under it.
Locks expire ${DEFAULT_TTL_MS / 60000} minutes after the last heartbeat.
Exit: 0 ok, 1 error, 2 busy (only without --wait, when nothing could be taken).`);
  process.exit(exit);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseArgs(argv) {
  const args = argv.slice(2);
  if (args.length === 0 || args[0] === "-h" || args[0] === "--help") usage(0);
  const command = args[0];
  const flags = {
    command,
    holder: null,
    wait: false,
    any: false,
    force: false,
    timeout: null,
    paths: [],
  };
  let i = 1;
  while (i < args.length) {
    const a = args[i];
    if (a === "--") {
      flags.paths.push(...args.slice(i + 1));
      break;
    }
    if (a === "--wait") flags.wait = true;
    else if (a === "--any") flags.any = true;
    else if (a === "--force") flags.force = true;
    else if (a === "--holder") flags.holder = args[++i];
    else if (a === "--timeout") flags.timeout = Number(args[++i]);
    else if (a.startsWith("-")) usage();
    else flags.paths.push(a);
    i++;
  }
  if (flags.timeout == null) flags.timeout = 0;
  if (!Number.isFinite(flags.timeout) || flags.timeout < 0) usage();
  return flags;
}

function posixRel(p) {
  const abs = path.resolve(ROOT, p);
  const rel = path.relative(ROOT, abs).split(path.sep).join("/");
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error(`path escapes repo: ${p}`);
  }
  return rel.replace(/\/+$/, "") || ".";
}

function pathsConflict(a, b) {
  if (a === b) return true;
  return a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
}

function ensureLockDir() {
  fs.mkdirSync(LOCK_DIR, { recursive: true });
}

function emptyRegistry() {
  return { locks: {} };
}

function readRegistry() {
  try {
    return JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf8"));
  } catch (err) {
    if (err.code === "ENOENT") return emptyRegistry();
    throw err;
  }
}

function writeRegistry(reg) {
  const tmp = `${REGISTRY_PATH}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(reg, null, 2)}\n`);
  fs.renameSync(tmp, REGISTRY_PATH);
}

function isStale(entry, now) {
  const ttl = entry.ttlMs ?? DEFAULT_TTL_MS;
  return now - (entry.heartbeatAt ?? entry.acquiredAt ?? 0) > ttl;
}

function sweepStale(reg, now) {
  const stolen = [];
  for (const [file, entry] of Object.entries(reg.locks)) {
    if (isStale(entry, now)) {
      stolen.push({ file, holder: entry.holder });
      delete reg.locks[file];
    }
  }
  return stolen;
}

function holdersFor(reg, files, holder) {
  const hits = [];
  for (const file of files) {
    for (const [locked, entry] of Object.entries(reg.locks)) {
      if (!pathsConflict(file, locked)) continue;
      if (entry.holder === holder) continue;
      hits.push({ file, locked, holder: entry.holder, heartbeatAt: entry.heartbeatAt });
    }
  }
  return hits;
}

async function withMutex(fn) {
  ensureLockDir();
  for (;;) {
    try {
      const fd = fs.openSync(MUTEX_PATH, "wx");
      try {
        fs.writeFileSync(fd, `${process.pid}\n`);
        return fn();
      } finally {
        fs.closeSync(fd);
        try {
          fs.unlinkSync(MUTEX_PATH);
        } catch {
          /* ignore */
        }
      }
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      try {
        const st = fs.statSync(MUTEX_PATH);
        if (Date.now() - st.mtimeMs > MUTEX_STALE_MS) fs.unlinkSync(MUTEX_PATH);
      } catch {
        /* ignore */
      }
      await sleep(50);
    }
  }
}

function formatBusy(hits) {
  return hits
    .map((h) => `  ${h.file}  held by ${h.holder} (covers ${h.locked})`)
    .join("\n");
}

function takeFiles(reg, holder, files, now) {
  for (const file of files) {
    for (const [locked, entry] of Object.entries(reg.locks)) {
      if (entry.holder !== holder) continue;
      if (locked === file || locked.startsWith(`${file}/`)) delete reg.locks[locked];
    }
  }
  const acquired = [];
  for (const file of files) {
    const covered = Object.entries(reg.locks).some(
      ([locked, entry]) => entry.holder === holder && (locked === file || file.startsWith(`${locked}/`)),
    );
    if (covered) {
      for (const entry of Object.values(reg.locks)) {
        if (entry.holder === holder) entry.heartbeatAt = now;
      }
      acquired.push(file);
      continue;
    }
    reg.locks[file] = { holder, acquiredAt: now, heartbeatAt: now, ttlMs: DEFAULT_TTL_MS };
    acquired.push(file);
  }
  return acquired;
}

function acquireOnce(holder, files, force, any) {
  const now = Date.now();
  const reg = readRegistry();
  const stolen = sweepStale(reg, now);
  if (force) {
    for (const file of files) {
      for (const [locked, entry] of Object.entries(reg.locks)) {
        if (pathsConflict(file, locked) && entry.holder !== holder) delete reg.locks[locked];
      }
    }
  }
  const hits = holdersFor(reg, files, holder);
  const busyPaths = new Set(hits.map((h) => h.file));
  const free = any ? files.filter((f) => !busyPaths.has(f)) : hits.length ? [] : files;
  if (!free.length) {
    writeRegistry(reg);
    return { ok: false, hits, stolen, acquired: [], pending: files };
  }
  const acquired = takeFiles(reg, holder, free, now);
  writeRegistry(reg);
  const pending = files.filter((f) => !acquired.includes(f));
  return { ok: true, stolen, acquired, pending, hits: pending.length ? holdersFor(reg, pending, holder) : [] };
}

async function acquire(flags) {
  if (!flags.holder) usage();
  const files = [...new Set(flags.paths.map(posixRel))].sort();
  if (!files.length) usage();
  const forever = flags.wait && flags.timeout === 0;
  const deadline = forever ? Infinity : Date.now() + flags.timeout * 1000;
  let lastLog = 0;
  let waited = false;

  for (;;) {
    const result = await withMutex(() => acquireOnce(flags.holder, files, flags.force, flags.any));
    if (result.stolen?.length) {
      for (const s of result.stolen) {
        console.warn(`stale lock stolen: ${s.file} (was ${s.holder})`);
      }
    }
    if (result.ok) {
      console.log(`acquired ${result.acquired.join(", ")} as ${flags.holder}`);
      if (result.pending.length) {
        console.log(`pending ${result.pending.join(", ")}`);
        if (result.hits.length) console.error(`still busy:\n${formatBusy(result.hits)}`);
      }
      return 0;
    }
    if (!flags.wait) {
      console.error(`busy:\n${formatBusy(result.hits)}`);
      console.error("retry with --any --wait — do not drop remaining objectives");
      return 2;
    }
    const now = Date.now();
    if (!waited || now - lastLog >= WAIT_LOG_MS) {
      console.error(`busy:\n${formatBusy(result.hits)}`);
      console.error(forever ? "waiting until free (no timeout)…" : `waiting ${POLL_MS / 1000}s…`);
      lastLog = now;
    }
    if (now >= deadline) {
      console.error(`timeout after ${flags.timeout}s waiting for ${files.join(", ")}`);
      console.error("retry: same acquire command — do not drop remaining objectives");
      return 2;
    }
    waited = true;
    await sleep(POLL_MS);
  }
}

async function release(flags) {
  if (!flags.holder) usage();
  const files = flags.paths.length ? [...new Set(flags.paths.map(posixRel))] : null;
  await withMutex(() => {
    const now = Date.now();
    const reg = readRegistry();
    sweepStale(reg, now);
    let n = 0;
    for (const [locked, entry] of Object.entries(reg.locks)) {
      if (entry.holder !== flags.holder) continue;
      if (files && !files.some((f) => pathsConflict(f, locked))) continue;
      delete reg.locks[locked];
      n++;
    }
    writeRegistry(reg);
    console.log(`released ${n} lock(s) for ${flags.holder}`);
  });
  return 0;
}

async function heartbeat(flags) {
  if (!flags.holder) usage();
  const now = Date.now();
  let n = 0;
  await withMutex(() => {
    const reg = readRegistry();
    sweepStale(reg, now);
    for (const entry of Object.values(reg.locks)) {
      if (entry.holder !== flags.holder) continue;
      entry.heartbeatAt = now;
      n++;
    }
    writeRegistry(reg);
  });
  if (!n) {
    console.error(`no locks held by ${flags.holder}`);
    return 1;
  }
  console.log(`heartbeat ${n} lock(s) for ${flags.holder}`);
  return 0;
}

async function status() {
  const now = Date.now();
  const { locks } = await withMutex(() => {
    const reg = readRegistry();
    sweepStale(reg, now);
    writeRegistry(reg);
    return reg;
  });
  const entries = Object.entries(locks);
  if (!entries.length) {
    console.log("no locks");
    return 0;
  }
  for (const [file, entry] of entries.sort(([a], [b]) => a.localeCompare(b))) {
    const age = Math.round((now - entry.heartbeatAt) / 1000);
    console.log(`${file}\tholder=${entry.holder}\tage=${age}s`);
  }
  return 0;
}

const flags = parseArgs(process.argv);
let code;
switch (flags.command) {
  case "acquire":
    code = await acquire(flags);
    break;
  case "release":
    code = await release(flags);
    break;
  case "heartbeat":
    code = await heartbeat(flags);
    break;
  case "status":
    code = await status();
    break;
  default:
    usage();
}
process.exit(code);
