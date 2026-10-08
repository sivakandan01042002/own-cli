# 🤖 QueryNest: Autonomous Multi-Agent Coding State Machine

QueryNest is an enterprise-hardened, autonomous, self-healing multi-agent software engineering framework and interactive CLI built on **LangGraph**, **Python**, **Prompt Toolkit**, **Rich**, and **Redis**.

It integrates specialized AI agents into a deterministic state graph capable of inspecting codebases, architecting blueprints, implementing features, running unit test suites, and autonomously fixing bugs through a closed-loop self-healing mechanism.

---

## 🏛️ Core Architectural Invariants

To eliminate context leakage, hallucination, and routing bugs, the system enforces three unbreakable design invariants across every turn:

> 1. **Request Seeding Invariant:** Every user request **MUST** populate `state["task"]` and append an initial `HumanMessage` containing the request and workspace context before any routing decision is executed.
> 2. **Repository Grounding Invariant:** Every agent that requires repository knowledge **MUST** have direct access to repository-aware tools (`list_directory`, `read_file`, `write_file`, `patch_file`, `search_code`, `run_git_command`) or verified repository context in state.
> 3. **State Persistence Invariant:** Every agent's verified output (`plan`, `coder_findings`, `test_results`, `fixer_analysis`) **MUST** be committed into `CodingAgentState` before graph control transitions to another node.

---

## 🏗️ Architecture & State Machine Flow

QueryNest routes user intent through a grounded state graph with automatic repository awareness, pre-tool confirmation gates, and self-healing validation:

```mermaid
flowchart TD
    START([User Prompt / Task]) --> triage{Input Triage<br/>triage_user_input}
    
    triage -- "Greeting / Pleasantry" --> greeting[Direct Response<br/>0 Tool Calls]
    triage -- "Slash Command" --> menu[Interactive Menu Picker<br/>Prompt Pre-fill]
    triage -- "Coding Task" --> router{Intent Router<br/>route_initial_intent}
    
    router -- "Question / Code Inspection" --> coder[2. Coder / Inspector Node<br/>Reads real repository files]
    router -- "Build / Feature Implementation" --> planner[1. Planner Node<br/>Architect Blueprint]
    
    planner --> plan_gate{Plan Permission Gate<br/>[1] Yes  [2] No}
    plan_gate -- "Yes, Do It" --> coder
    plan_gate -- "No, Cancel" --> cancel[Cancel Workflow]
    
    coder -->|should_continue_coder| tool_check{Tools Requested?}
    tool_check -- "Tool calls present" --> tool_gate{Pre-Tool Permission Gate<br/>[1] Yes  [2] No}
    tool_gate -- "Yes, Do It" --> tools[3. Tool Execution Node<br/>17 Physical Tools & APIs]
    tool_gate -- "No, Cancel" --> cancel_tool[Cancel Tool Execution]
    tools --> coder
    
    tool_check -- "Code Modified (write_file/patch_file)" --> validator[4. Validator Node<br/>Pytest Test Runner]
    tool_check -- "Read-Only / Explanation" --> summarizer[6. Summarizer Node<br/>Direct Factual Report]
    
    validator -->|should_retry_or_finish| test_check{Tests Passed?}
    test_check -- "Failed ❌ & Retries < 3" --> fixer[5. Fixer Node<br/>Root-Cause Debugger]
    fixer --> coder
    test_check -- "Passed ✅ or Max Retries" --> summarizer
    
    summarizer --> END([Final Verified Output])
```

---

## 👥 The 6 Graph Nodes

| Node | Specialist Role | Mission & Tools | State Contract Updates |
| :--- | :--- | :--- | :--- |
| **`planner`** | 🏗️ Senior Software Architect | Deconstructs coding tasks against live `repository_tree` into clean architectural blueprints. Pure planning — never writes code. | `plan`, `retry_count=0`, `test_passed=False` |
| **`coder`** | 💻 Senior Full-Stack Developer | Inspects workspace files, patches code, runs safe Git workflows, executes terminal commands, or runs browser tests based on evidence. | `messages` (tool calls), `coder_findings`, `modified_files` |
| **`tools`** | ⚙️ Tool Execution Node | Prebuilt LangGraph `ToolNode` executing 17 tools across filesystem, Git, shell, DuckDuckGo, Multimodal Vision, and Playwright. | `ToolMessage` (tool outputs) |
| **`validator`** | 🧪 QA & Test Inspector | Executes `pytest` in an isolated subprocess to verify implementation correctness against unit tests. | `test_results`, `test_passed` (bool) |
| **`fixer`** | 🩹 Debugger & QA Lead | Triggered on test failure. Analyzes tracebacks, isolates root cause, and provides precise surgical patch instructions. | `retry_count += 1`, `fixer_analysis`, fix instructions in `messages` |
| **`summarizer`** | 📋 Technical Writer | Reconciles actual modified files against `git status` and streams the final verification report. | `final_summary`, `modified_files` |

---

## 🛡️ Production Hardening & Security Architecture

QueryNest enforces physical, runtime-level security controls rather than relying merely on prompt rules:

1. **Canonical Path Sandboxing (`assert_inside_workspace`):**
   * Uses canonical path resolution (`Path.resolve()`) and `is_relative_to(workspace_root)` to block path traversal (`../../`), prefix collision attacks (`/workspace-attacker`), and symlink escapes.
2. **Subprocess Environment Allowlist Isolation:**
   * Child subprocesses receive only allowlisted system variables (`ENV_ALLOWLIST` containing `PATH`, `USERPROFILE`, `HOME`, `SystemRoot`, `CONDA_*`, `VIRTUAL_ENV`). Secrets (`*_API_KEY`, `*_SECRET`, `*_TOKEN`) are never inherited.
3. **Subprocess Hard Limits & Tree Termination:**
   * Automatic cross-platform process tree termination (`taskkill /F /T` / `os.killpg`) on timeout, with a 50KB output buffer limit to prevent memory exhaustion.
4. **Untrusted Content Quarantine Envelope:**
   * Repository files, web search outputs, and scraped HTML documentation are quarantined inside `<untrusted_repository_content source="...">` envelopes.
5. **Atomic Workspace Concurrency Locking (`WorkspaceLock`):**
   * Employs atomic `os.open(..., os.O_CREAT | os.O_EXCL)` to eliminate race conditions between simultaneous CLI sessions operating on the same workspace.
6. **Multi-Provider LLM Resilience:**
   * `resilient_llm_invoke` provides exponential backoff on 429/503 errors with automated failover (Gemini $\rightarrow$ Groq).
7. **Structured Audit Logging:**
   * Append-only `~/.querynest/workspaces/<hash>/logs/audit.jsonl` tracks all planner decisions, tool invocations, and test validations.

---

## 🛠️ Complete 17-Tool Arsenal (`app/integrations/tools/`)

| Category | Tool | Signature | Description |
| :--- | :--- | :--- | :--- |
| **File Operations** | `list_directory` | `dir_path: str = "."` | Explores workspace files, respecting `DEFAULT_IGNORE_DIRS`. |
| | `read_file` | `file_path: str` | Reads file content with line numbers (quarantined). |
| | `write_file` | `file_path: str, content: str` | Creates or overwrites files on disk with diff rendering. |
| | `patch_file` | `file_path: str, target_content: str, replacement_content: str` | Surgically replaces specific code blocks without full rewrite. |
| | `delete_file` | `file_path: str` | Safely removes files from the workspace. |
| | `search_code` | `query: str, path: str = ".", file_pattern: str = "*"` | Fast Grep & symbol scanner across workspace files. |
| **Git & Version Control** | `run_git_command` | `subcommand: str, timeout: int = 30` | Safe git execution (`status`, `diff`, `branch`, `commit`, `log`). |
| **Terminal & Testing** | `run_terminal_command` | `command: str, timeout: int = 60` | Executes shell commands in an allowlist-isolated subprocess. |
| | `run_pytest` | `test_path: str = ""` | Runs pytest test suite and captures exit codes and tracebacks. |
| **Web Research** | `search_web` | `query: str, max_results: int = 5` | DuckDuckGo search integration cached in Redis. |
| | `read_doc_url` | `url: str, max_length: int = 5000` | Scrapes external documentation or API guides into clean text. |
| **Vision & Image AI** | `inspect_image` | `image_path: str, prompt: str = "..."` | Multimodal Vision inspection of UI mockups, diagrams, and screenshots. |
| | `generate_image` | `prompt: str, output_path: str = "", width: int = 1024, height: int = 1024` | Generates high-resolution images via Flux.1/SDXL and saves to disk. |
| **Browser Testing** | `browser_open` | `url: str, wait_seconds: int = 2` | Loads live web apps or local servers in headless Chromium. |
| | `browser_screenshot` | `output_path: str = ""` | Captures full-page screenshots of active browser DOM for visual QA. |
| | `browser_click` | `selector: str` | Clicks interactive buttons, links, or tabs on web pages. |
| | `browser_type` | `selector: str, text: str` | Types text into input fields and forms in the active browser. |

---

## ⚡ Slash Commands Guide

| Command | Description |
| :--- | :--- |
| `/help` | Opens the interactive command picker with arrow-key navigation and prompt pre-fill. |
| `/sessions` / `/session` | Lists past conversation threads stored in Redis / local disk; selecting one restores full chat history. |
| `/session clear` | Clears all stored session threads from Redis and local cache. |
| `/new` | Starts a fresh multi-turn conversation session. |
| `/model` | Interactively inspects or switches the active AI model. |
| `/mode` | Toggles execution mode (`normal` permission gate vs `accept-edits` auto-execution). |
| `/tools` | Lists all 17 registered tools and their functional signatures. |
| `/history` | Displays task history for the current terminal session. |
| `/clear` | Clears the terminal screen. |
| `/exit` / `/quit` | Gracefully closes QueryNest. |

---

## 🚀 Getting Started

### 1. Prerequisites & Environment
```bash
# Clone repository
cd ai-learning-multi-agent

# Activate environment
conda activate ai_app_env

# Configure environment variables
cp backend/.env.example backend/.env
```

### 2. Configuration (`backend/.env`)
```env
# LLM API Keys
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIzaSy...

# Provider selection: 'groq' or 'gemini'
DEFAULT_PROVIDER=gemini

# Redis Session Storage (Optional - falls back to local ~/.querynest/ disk storage)
REDIS_URL=rediss://default:your_token@your-host.upstash.io:6379
```

### 3. Running the CLI
```bash
# Start the interactive chat interface
python backend/app/cli.py chat

# Or run a single task directly
python backend/app/cli.py run "Build a REST API with FastAPI"
```
