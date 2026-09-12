# AI Agent Studio Local Start Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one `start.sh` command that validates the local environment, starts the FastAPI backend and Next.js frontend together, and cleans up both processes on exit.

**Architecture:** A Bash coordinator lives above the two repositories so it can locate both projects relative to itself. A separate Bash behavior test copies the coordinator into a temporary fake project, replaces external commands with deterministic fakes, and verifies preflight failure and child-process cleanup without touching real services.

**Tech Stack:** Bash 3.2-compatible shell, FastAPI/Uvicorn, pnpm/Next.js, curl, lsof

---

### Task 1: Add executable behavior tests

**Files:**
- Create: `/Users/wtf/Desktop/agent-studio/tests/start_test.sh`
- Test: `/Users/wtf/Desktop/agent-studio/tests/start_test.sh`

- [ ] **Step 1: Write the failing test harness**

Create a temporary `Agent-Studio` and `Agent-Studio-web` layout, fake `python`, `pnpm`, and `lsof` commands, then assert that `start.sh`:

```bash
bash "$PROJECT_ROOT/start.sh" >"$output_file" 2>&1 &
launcher_pid=$!
wait_for_text "$output_file" "前端：http://127.0.0.1:4000"
kill -INT "$launcher_pid"
wait "$launcher_pid" || true
assert_file "$fake_runtime/terminated-backend"
assert_file "$fake_runtime/terminated-frontend"
```

Also remove the fake virtual-environment Python and assert a non-zero exit containing `未找到后端虚拟环境`.

- [ ] **Step 2: Run the test and verify it fails because the launcher is missing**

Run: `bash /Users/wtf/Desktop/agent-studio/tests/start_test.sh`

Expected: FAIL because `/Users/wtf/Desktop/agent-studio/start.sh` does not exist.

- [ ] **Step 3: Commit the red test**

The parent directory is not a Git repository, so retain the test as an uncommitted project-level utility rather than committing it into either child repository.

### Task 2: Implement the coordinator

**Files:**
- Create: `/Users/wtf/Desktop/agent-studio/start.sh`

- [ ] **Step 1: Implement preflight checks**

Resolve the script directory using `BASH_SOURCE[0]`; validate project directories, `.venv/bin/python`, `.env`, `pnpm`, `node_modules`, and ports `4000` and `7100`. Return actionable Chinese error messages without starting a child process.

- [ ] **Step 2: Implement supervised startup**

Start both commands directly and capture their process IDs:

```bash
"$BACKEND_PYTHON" -c \
  'import os, sys; os.chdir(sys.argv[1]); os.execv(sys.argv[2], sys.argv[2:])' \
  "$BACKEND_DIR" "$BACKEND_PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 7100 &

pnpm --dir "$FRONTEND_DIR" dev &
```

Capture both PIDs, trap `INT`, `TERM`, and `EXIT`, terminate only those process groups, and wait until either process exits.

- [ ] **Step 3: Run behavior tests**

Run: `bash /Users/wtf/Desktop/agent-studio/tests/start_test.sh`

Expected: PASS for preflight validation, address output, and cleanup behavior.

- [ ] **Step 4: Run shell syntax validation**

Run: `bash -n /Users/wtf/Desktop/agent-studio/start.sh /Users/wtf/Desktop/agent-studio/tests/start_test.sh`

Expected: exit status 0 with no output.

### Task 3: Verify against the real application

**Files:**
- Verify: `/Users/wtf/Desktop/agent-studio/start.sh`

- [ ] **Step 1: Make the launcher executable**

Run: `chmod +x /Users/wtf/Desktop/agent-studio/start.sh`

- [ ] **Step 2: Start both real services**

Run: `/Users/wtf/Desktop/agent-studio/start.sh`

Expected: backend and frontend report ready on ports `7100` and `4000`.

- [ ] **Step 3: Probe both services**

Run: `curl -fsS http://127.0.0.1:7100/health`

Expected: successful JSON health response.

Run: `curl -fsSI http://127.0.0.1:4000`

Expected: HTTP success response.

- [ ] **Step 4: Stop and verify cleanup**

Send `Ctrl+C` to the launcher, then run:

```bash
lsof -nP -iTCP:7100 -sTCP:LISTEN
lsof -nP -iTCP:4000 -sTCP:LISTEN
```

Expected: neither command reports a listening process created by this run.
