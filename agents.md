# 🤖 Agents & Tools Quick Reference Guide

A quick reference guide for the multi-agent system implemented in this workspace.

---

## 👥 Agents

### 1. 🏗️ Planner Agent (`planner_node`)
* **Role:** Software Architect / Technical Planner
* **Mission:** Deconstructs coding tasks against live `repository_tree` into clean architectural blueprints with file specifications, safety permissions, test plans, and verification commands.
* **Input:** `state["task"]`, `state["repository_tree"]`, `state["workspace_root"]`
* **Output:** `state["plan"]`, initializes `state["retry_count"] = 0`, `state["test_passed"] = False`

### 2. 💻 Coder Agent (`coder_node`)
* **Role:** Implementation & Automation Engineer
* **Mission:** Inspects existing project files, implements requested features, executes safe Git commands, generates documents/resumes, runs terminal commands (npm, pip, docker, curl, powershell), inspects visual images/mockups with Multimodal Vision, generates AI images from prompts, tests live web applications with Playwright browser tools, searches symbols with code grep, surgically patches code blocks, reads documentation URLs, writes unit tests, or explains project code based on verified evidence.
* **Tools Used:** 17 physical tools (`write_file`, `read_file`, `patch_file`, `delete_file`, `list_directory`, `search_code`, `search_web`, `read_doc_url`, `run_git_command`, `run_terminal_command`, `run_pytest`, `inspect_image`, `generate_image`, `browser_open`, `browser_screenshot`, `browser_click`, `browser_type`)
* **Output:** `state["messages"]` (with tool calls for file inspection/creation/git/terminal/vision/image gen/browser), `state["coder_findings"]`, `state["modified_files"]`

### 3. ⚙️ Tool Execution Node (`tool_node`)
* **Role:** Python Execution Engine (Prebuilt LangGraph `ToolNode`)
* **Mission:** Physically executes tool calls on disk, over HTTP, with headless Chromium, or through Multimodal Vision APIs and feeds outputs back into conversation memory.

### 4. 🧪 Validator Agent (`validator_node`)
* **Role:** QA & Test Inspector
* **Mission:** Runs `pytest` in an allowlist-isolated background subprocess to test newly created code against unit tests.
* **Output:** `state["test_passed"]` (`True`/`False`), `state["test_results"]`

### 5. 🩹 Fixer Agent (`fixer_node`)
* **Role:** Debugging & Root-Cause QA Specialist
* **Mission:** Triggered on test failure. Analyzes tracebacks, isolates the bug, and gives precise fix instructions back to the Coder.
* **Output:** `state["retry_count"] += 1`, `state["fixer_analysis"]`, fix instructions appended to `state["messages"]`

### 6. 📋 Summarizer Agent (`summarizer_node`)
* **Role:** Technical Reporter & Documentation Specialist
* **Mission:** Reconciles actual modified files with `git status` output and formats the final user-facing completion report based ONLY on verified findings.
* **Output:** `state["final_summary"]`, `state["modified_files"]`


---

## 🔀 Decision Edges

1. **`route_initial_intent` (At `START`)**:
   * **Question / Code Explanation / Image Query** (*"what is the purpose of cli.py?"* or *"describe @image screenshot.png"*) $\rightarrow$ `coder` (Direct project inspection, skips Planner & Pytest).
   * **Coding / Build Task** (*"build a REST API"*) $\rightarrow$ `planner` (Architecture blueprint).

2. **`should_continue_coder` (After `coder`)**:
   * Has tool calls $\rightarrow$ `tools` $\rightarrow$ `coder` (Loop).
   * Code was modified (`write_file`, `patch_file`, or `delete_file` called) $\rightarrow$ `validator` (Runs Pytest).
   * No code modified (read-only/Git/Vision/Q&A) $\rightarrow$ `summarizer` (Direct answer, skips Pytest).

3. **`should_retry_or_finish` (After `validator`)**:
   * Tests Passed $\rightarrow$ `summarizer` $\rightarrow$ `END`.
   * Tests Failed & Retries $< 3 \rightarrow$ `fixer` $\rightarrow$ `coder` (Self-Healing Loop).
   * Tests Failed & Retries $\ge 3 \rightarrow$ `summarizer` $\rightarrow$ `END`.

---

## 🛠️ Tools (Complete 17-Tool Set)

| Tool | Signature | Purpose |
| :--- | :--- | :--- |
| `list_directory` | `dir_path: str = "."` | Explore project file hierarchy |
| `read_file` | `file_path: str` | Read source code with line numbers (quarantined) |
| `write_file` | `file_path: str, content: str` | Create or update files/documents/scripts on disk |
| `patch_file` | `file_path: str, target_content: str, replacement_content: str` | Surgically replace code blocks without rewriting whole file |
| `delete_file` | `file_path: str` | Delete file from workspace |
| `search_code` | `query: str, path: str = ".", file_pattern: str = "*"` | Fast Grep & symbol search across repository |
| `run_git_command` | `subcommand: str, timeout: int = 30` | Safe git execution (status, diff, branch, commit, log) |
| `run_terminal_command` | `command: str, timeout: int = 60` | Shell commands in allowlist-isolated subprocess |
| `run_pytest` | `test_path: str = ""` | Run pytest suite and capture output |
| `search_web` | `query: str, max_results: int = 5` | DuckDuckGo search for live docs (Cached in Redis) |
| `read_doc_url` | `url: str, max_length: int = 5000` | Scrapes external web links or API docs as clean text |
| `inspect_image` | `image_path: str, prompt: str = "..."` | Multimodal Vision inspection of UI mockups, diagrams, and screenshots (Cached in Redis) |
| `generate_image` | `prompt: str, output_path: str = "", width: int = 1024, height: int = 1024` | Generates AI images from text prompts using Flux.1/SDXL and saves to disk |
| `browser_open` | `url: str, wait_seconds: int = 2` | Opens web page or local development server in headless Chromium |
| `browser_screenshot` | `output_path: str = ""` | Captures full-page screenshots of active web apps for visual verification |
| `browser_click` | `selector: str` | Clicks interactive buttons, links, or form controls in browser |
| `browser_type` | `selector: str, text: str` | Types text into web inputs, search bars, and forms |

---

## 🛡️ Reliability & Guardrail Rules

1. **Strict Tool Name Enforcement & Sanitization**:
   * The Coder agent is strictly restricted to the 17 tools listed above.
   * `coder_node` automatically sanitizes `tool_calls` by filtering out any hallucinated tool names before handing off to `ToolNode`, preventing runtime validation crashes.

2. **Canonical Path Sandboxing & Untrusted Quarantine**:
   * All file and browser operations use `assert_inside_workspace` (`is_relative_to`) to prevent path traversal, prefix collisions, or symlink escapes.
   * Read files, web results, and scraped pages are quarantined in `<untrusted_repository_content>` tags.

3. **Subprocess Allowlist Isolation & Tree Killing**:
   * Child subprocesses only receive allowlisted environment variables (`PATH`, `USERPROFILE`, `HOME`, `SystemRoot`, `CONDA_*`, `VIRTUAL_ENV`). Secrets are never inherited.
   * On timeout, cross-platform process tree termination (`taskkill /F /T` / `os.killpg`) terminates all spawned child processes.

4. **Zero-Cost Multimodal & Web Search Caching**:
   * `inspect_image` and `search_web` automatically cache results by SHA-256 / MD5 hash in Redis, ensuring 0 repeat API calls and 0 token waste.
