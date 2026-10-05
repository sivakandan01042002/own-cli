# 🤖 Agents & Tools Quick Reference Guide

A quick reference guide for the multi-agent system implemented in this workspace.

---

## 👥 Agents

### 1. 🏗️ Planner Agent (`planner_node`)
* **Role:** Senior Software Architect
* **Mission:** Deconstructs the user task into a clean architectural blueprint with file specifications, test plans, and verification commands.
* **Input:** `state["task"]`
* **Output:** `state["plan"]`, initializes `state["retry_count"] = 0`

### 2. 💻 Coder Agent (`coder_node`)
* **Role:** Senior Software Engineer
* **Mission:** Follows the blueprint to generate production-quality code and comprehensive unit tests.
* **Tools Used:** `write_file`, `read_file`, `list_directory`, `search_web`
* **Output:** `state["messages"]` (with tool calls for file creation)

### 3. ⚙️ Tool Execution Node (`tool_node`)
* **Role:** Python Execution Engine (Prebuilt LangGraph `ToolNode`)
* **Mission:** Physically executes tool calls on disk or over HTTP and feeds outputs back into conversation memory.

### 4. 🧪 Validator Agent (`validator_node`)
* **Role:** QA & Test Inspector
* **Mission:** Runs `pytest` in a background subprocess to test newly created code against unit tests.
* **Output:** `state["test_passed"]` (`True`/`False`), `state["test_results"]`

### 5. 🩹 Fixer Agent (`fixer_node`)
* **Role:** Debugger & QA Lead
* **Mission:** Triggered on test failure. Analyzes tracebacks, isolates the bug, and gives precise fix instructions back to the Coder.
* **Output:** `state["retry_count"] += 1`, fix instructions appended to `state["messages"]`

### 6. 📋 Summarizer Agent (`summarizer_node`)
* **Role:** Technical Writer & Presenter
* **Mission:** Formats the final user-facing completion report with features implemented, files created, and test verification proof.
* **Output:** `state["final_summary"]`

---

## 🔀 Decision Edges

1. **`should_continue_coder`**:
   * Has tool calls $\rightarrow$ `tools` $\rightarrow$ `coder` (Loop)
   * No tool calls $\rightarrow$ `validator`

2. **`should_retry_or_finish`**:
   * Tests Passed $\rightarrow$ `summarizer` $\rightarrow$ `END`
   * Tests Failed & Retries $< 3 \rightarrow$ `fixer` $\rightarrow$ `coder` (Self-Healing Loop)
   * Tests Failed & Retries $\ge 3 \rightarrow$ `summarizer` $\rightarrow$ `END`

---

## 🛠️ Tools

| Tool | Signature | Purpose |
| :--- | :--- | :--- |
| `list_directory` | `dir_path: str = "."` | Explore project file hierarchy |
| `read_file` | `file_path: str` | Read source code with line numbers |
| `write_file` | `file_path: str, content: str` | Create or update file on disk |
| `delete_file` | `file_path: str` | Delete file from workspace |
| `run_terminal_command` | `command: str, timeout: int = 30` | Run shell command via subprocess |
| `run_pytest` | `test_path: str = ""` | Run pytest suite and capture output |
| `search_web` | `query: str, max_results: int = 5` | DuckDuckGo search for live docs |
