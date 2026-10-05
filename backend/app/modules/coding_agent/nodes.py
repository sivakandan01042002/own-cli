from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import ToolNode
from app.core.llm import get_llm
from app.integrations.tools import ALL_TOOLS
from app.integrations.tools.terminal_tools import run_pytest
from app.modules.coding_agent.state import CodingAgentState
from app.modules.coding_agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
    FIXER_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
)


# Initialize the base LLM for reasoning
base_llm = get_llm()

# Bind tools to the LLM so the Coder agent can create/read files and search the web
coder_llm = base_llm.bind_tools(ALL_TOOLS)


def planner_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Architect Node: Analyzes the user's task and produces a structured blueprint.
    """
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"User Task:\n{state['task']}"),
    ]

    # Call the model to generate the architecture plan
    response = base_llm.invoke(messages)

    # Return the state updates
    return {
        "plan": response.content,
        "messages": [response],
        "retry_count": 0,
        "test_passed": False,
        "modified_files": [],
    }


def coder_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Coder Node: Executes the plan by generating code, tests, or emitting tool calls.
    """
    system_msg = SystemMessage(content=CODER_SYSTEM_PROMPT)
    messages = [system_msg] + state["messages"]

    # The LLM inspects the history and decides whether to write files or respond with text
    response = coder_llm.invoke(messages)

    return {"messages": [response]}


# Prebuilt LangGraph ToolNode that executes any tool calls on disk/web
tool_node = ToolNode(ALL_TOOLS)


def validator_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Validator Node: Reads test target from state and executes pytest in the workspace.
    """
    # Explicitly check state for a specific test file/target
    target_test = state.get("test_command") or ""

    test_output = run_pytest.invoke({"test_path": target_test})

    # Check if pytest exited with code 0 and has no failure keywords
    passed = "Exit Code: 0" in test_output and "failed" not in test_output.lower()

    return {
        "test_results": test_output,
        "test_passed": passed,
    }


def fixer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Fixer / Debugger Node: Analyzes test failure tracebacks and instructs the Coder on what to fix.
    """
    current_retry = state.get("retry_count", 0) + 1
    test_results = state.get("test_results", "No test output available.")

    prompt_content = (
        f"The tests failed on attempt {current_retry}.\n\n"
        f"Here is the pytest failure output and traceback:\n"
        f"```text\n{test_results}\n```\n\n"
        f"Please analyze the exact root cause and give the Coder precise fix instructions."
    )

    messages = [
        SystemMessage(content=FIXER_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    response = base_llm.invoke(messages)

    fix_instruction = HumanMessage(
        content=f"⚠️ Test Failure Analysis & Fix Instructions (Attempt {current_retry}):\n{response.content}"
    )

    return {
        "retry_count": current_retry,
        "messages": [fix_instruction],
    }


def summarizer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Summarizer Node: Formats the final user-facing completion report.
    """
    task = state.get("task", "")
    plan = state.get("plan", "")
    test_results = state.get("test_results", "")
    test_passed = state.get("test_passed", False)
    retry_count = state.get("retry_count", 0)

    summary_prompt = (
        f"Original Task: {task}\n\n"
        f"Architecture Plan:\n{plan}\n\n"
        f"Final Verification Status: {'Passed ✅' if test_passed else 'Failed ❌'} (Total Retries: {retry_count})\n\n"
        f"Test Output Summary:\n{test_results}\n\n"
        f"Please write the final markdown summary for the user."
    )

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
        HumanMessage(content=summary_prompt),
    ]

    response = base_llm.invoke(messages)
    return {"final_summary": response.content}






