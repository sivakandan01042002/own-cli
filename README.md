# 🤖 QueryNest: Autonomous Multi-Agent Coding State Machine

QueryNest is an autonomous, self-healing multi-agent software engineering framework and interactive CLI built on **LangGraph**, **Python**, **Prompt Toolkit**, **Rich**, and **Redis**.

It integrates specialized AI agents into a deterministic state graph capable of inspecting existing codebases, architecting blueprints, creating features, running unit test suites, and autonomously fixing bugs through a closed-loop self-healing mechanism.

---

## 🏛️ Core Architectural Invariants

To eliminate context leakage, hallucination, and routing bugs, the system enforces three unbreakable design invariants across every turn:

> 1. **Request Seeding Invariant:** Every user request **MUST** populate `state["task"]` and append an initial `HumanMessage` containing the request and workspace context before any routing decision is executed.
> 2. **Repository Grounding Invariant:** Every agent that requires repository knowledge **MUST** have direct access to repository-aware tools (`list_directory`, `read_file`, `write_file`, `run_git_command`) or verified repository context in state.
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
    tool_gate -- "Yes, Do It" --> tools[3. Tool Execution Node<br/>Disk CRUD, Git & Terminal Tools]
    tool_gate -- "No, Cancel" --> cancel_tool[Cancel Tool Execution]
    tools --> coder
    
    tool_check -- "Code Modified (write_file)" --> validator[4. Validator Node<br/>Pytest Test Runner]
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
| **`coder`** | 💻 Senior Software Engineer | Inspects real workspace files with tools, executes safe Git workflows, implements code & unit tests, or explains project code. | `messages` (tool calls), `coder_findings` |
| **`tools`** | ⚙️ Tool Execution Node | Prebuilt LangGraph `ToolNode` that executes tool calls on disk, via git, or over HTTP and injects results back into conversation memory. | `ToolMessage` (tool outputs) |
| **`validator`** | 🧪 QA & Test Inspector | Executes `pytest` in a background subprocess to test newly created code against unit test suites. | `test_results`, `test_passed` (bool) |
| **`fixer`** | 🩹 Debugger & QA Lead | Triggered on test failure. Analyzes tracebacks, isolates true root causes from symptoms, and gives precise fix instructions. | `retry_count += 1`, `fixer_analysis`, fix instructions in `messages` |
| **`summarizer`** | 📋 Technical Writer | Produces a clean, factual completion report based ONLY on verified tool executions and test outputs. | `final_summary` |

---

## 🔀 Smart Decision Routing (Edges)

1. **`route_initial_intent` (At `START`)**:
   * **Question / Code Inspection** (*"what's the purpose of cli.py?"*, *"how does routing work?"*) $\rightarrow$ `coder` (Direct inspection with tools, skips Planner & Pytest).
   * **Coding / Build Task** (*"build a REST API"*, *"add JWT auth"*) $\rightarrow$ `planner` (Full architectural blueprint).

2. **`should_continue_coder` (After `coder`)**:
   * **Has Tool Calls** $\rightarrow$ `tools` $\rightarrow$ `coder` (Re-enters Coder with tool output).
   * **Code was Modified** (`write_file` or `delete_file` executed) $\rightarrow$ `validator` (Runs Pytest).
   * **No Code Modified** (Read-only Q&A or explanation) $\rightarrow$ `summarizer` (Direct answer, bypasses Pytest).

3. **`should_retry_or_finish` (After `validator`)**:
   * **Tests Passed (`Exit Code: 0`)** $\rightarrow$ `summarizer` $\rightarrow$ `END`.
   * **Tests Failed & Retries $< 3$** $\rightarrow$ `fixer` $\rightarrow$ `coder` (Self-Healing Loop).
   * **Tests Failed & Retries $\ge 3$** $\rightarrow$ `summarizer` $\rightarrow$ `END` (Report failures transparently).

---

## 🧠 Centralized State Schema (`state.py`)

LangGraph operates over a strongly-typed state schema:

```python
class CodingAgentState(TypedDict):
    # 1. User Request & Conversation History (with LangGraph append reducer)
    task: str
    messages: Annotated[List[BaseMessage], add_messages]

    # 2. Repository & Workspace Context
    workspace_root: str
    repository_tree: Optional[str]

    # 3. Planning & Architecture Blueprint
    plan: Optional[str]

    # 4. Coding & Inspection Findings
    coder_findings: List[str]
    modified_files: List[str]

    # 5. Testing, Verification & Self-Healing
    test_command: Optional[str]
    test_results: Optional[str]
    test_passed: bool
    fixer_analysis: Optional[str]
    retry_count: int

    # 6. Final User Completion Report
    final_summary: Optional[str]
```

---

## 🛠️ Registered Tool Arsenal (`app/integrations/tools/`)

| Tool | Signature | Description |
| :--- | :--- | :--- |
| `list_directory` | `dir_path: str = "."` | Lists directory structure, filtering `.git`, `__pycache__`, `.venv`. |
| `read_file` | `file_path: str` | Reads file content with line numbers for inspection and debugging. |
| `write_file` | `file_path: str, content: str` | Creates or updates files on disk, auto-creating missing directories. |
| `delete_file` | `file_path: str` | Safely removes files from the workspace. |
| `run_git_command` | `subcommand: str, timeout: int = 30` | Safe git execution (`status`, `diff`, `branch`, `commit`, `log`) with UTF-8 encoding. |
| `run_terminal_command` | `command: str, timeout: int = 60` | Executes shell commands in a sandboxed subprocess. |
| `run_pytest` | `test_path: str = ""` | Runs pytest test suite and captures exit codes, stdout, and tracebacks. |
| `search_web` | `query: str, max_results: int = 5` | DuckDuckGo search integration cached in Redis. |

---

## 💻 Interactive Terminal UI (`app/cli.py` & `app/ui/`)

QueryNest includes a framed terminal CLI built on **Prompt Toolkit** and **Rich**, modularized under `app/ui/`:

* **Interactive Arrow-Key Menu Picker (`menu.py`):**
  * Full terminal arrow navigation (`↑` / `↓` or `k` / `j`) with active blue pointer (`  > `).
  * Auto-erasure on select/dismiss (`erase_when_done=True`) leaving a pristine terminal history.
* **Prompt Buffer Pre-Filling (`cli.py`):**
  * Selecting a previous task from `/sessions` or a command from `/help` automatically loads it into the input prompt buffer (`❯ <selected_item>`), ready for immediate execution or editing.
* **Pre-Tool Permission Confirmation Gate (`dialogs.py`):**
  * Displays requested tool actions (e.g. `Git: git status`) and prompts for confirmation (`[1] Yes, Do It`, `[2] No, Cancel / Skip`) before executing dangerous disk or git modifications.
* **Semantic Triage & Anti-Overwork Guardrails (`guardrails.py`):**
  * Classifies natural language inputs. Expressions of appreciation (*"Great work. Thanks!"*, *"looks good"*) are triaged as greetings with 0 tool calls and no unprompted git commits.
* **Framed Native Input Prompt (`prompt.py`):**
  * Native top and bottom window dividers (`Window(char="─")`) framing the active input line, with floating autocomplete dropdown for `/` commands.
* **Live Shimmer Wave Animations (`shimmer.py`):**
  * Real-time animated cement wave with green shimmering dots during active tool execution (`Reading file...`, `Running command...`, `Analyzing codebase...`).
* **Live Markdown Streaming (`markdown_stream.py`):**
  * Streams LLM responses with bold white section headings and rounded boxed tables.
* **Session Persistence (`redis_client.py`):**
  * Automatically records completed task sessions to Redis with relative elapsed timestamps (`just now`, `15m ago`, `2h ago`).

---

## ⚡ Slash Commands Guide

| Command | Description |
| :--- | :--- |
| `/help` | Opens the interactive command picker with arrow-key navigation and prompt pre-fill. |
| `/sessions` / `/session` | Opens the interactive session picker displaying previous tasks and relative elapsed time. |
| `/session clear` | Clears all stored session records from Redis. |
| `/model` | Displays the currently active LLM provider and model ID. |
| `/model gemini` | Switches active model to **Google Gemini 2.0 Flash**. |
| `/model groq` | Switches active model to **Groq GPT-OSS 120B**. |
| `/tools` | Lists all 8 registered tools and their functional signatures. |
| `/history` | Displays task history for the current terminal session. |
| `/clear` | Clears the terminal screen. |
| `/exit` / `/quit` | Gracefully closes QueryNest. |

---

## 🚀 Getting Started

### 1. Prerequisites & Environment
```bash
# Clone repository
cd ai-learning-multi-agent

# Create or activate Conda environment
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

# Redis Session Storage (Upstash or Local)
REDIS_URL=rediss://default:your_token@your-host.upstash.io:6379
```

### 3. Running the CLI
```bash
# Start the interactive chat interface
python backend/app/cli.py chat

# Or run a single task directly
python backend/app/cli.py run "Build a REST API with FastAPI"
```
