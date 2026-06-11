import time
import operator
import os
from typing import Annotated, TypedDict, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# Initialize LLM
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# --- 1. State Definitions ---

class SequentialState(TypedDict):
    task_goal: str
    plan: List[str] # Tasks remaining
    completed_steps: Annotated[List[str], operator.add]
    generated_code: Annotated[List[str], operator.add]
    total_tokens: Annotated[int, operator.add]

class DistributedState(TypedDict):
    task_goal: str
    plan: List[str]
    generated_code: Annotated[List[str], operator.add]
    total_tokens: Annotated[int, operator.add]
    
# State for a single parallel worker in the distributed plan
class WorkerState(TypedDict):
    task_description: str
    task_goal: str

# --- 2. Sequential Nodes ---

def sequential_worker(state: SequentialState):
    plan = state["plan"]
    if not plan:
        return {} # Should not happen if we route correctly
    
    current_task = plan[0]
    remaining_plan = plan[1:]
    
    # Execute with LLM
    messages = [
        SystemMessage(content=f"You are a coding assistant. Your overall goal is: {state['task_goal']}"),
        HumanMessage(content=f"Please implement this specific step: {current_task}\nReturn ONLY the code.")
    ]
    response = llm.invoke(messages)
    
    # Extract token usage directly from the response metadata
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    
    return {
        "plan": remaining_plan,
        "completed_steps": [current_task],
        "generated_code": [response.content],
        "total_tokens": tokens
    }

def sequential_router(state: SequentialState):
    if len(state["plan"]) == 0:
        return END
    return "worker"

# --- 3. Distributed Nodes ---

def distributed_dispatcher(state: DistributedState):
    # This node dynamically spins up a worker for each item in the plan in parallel
    sends = []
    for task in state["plan"]:
        sends.append(
            Send("parallel_worker", {
                "task_description": task,
                "task_goal": state["task_goal"]
            })
        )
    return sends

def parallel_worker(state: WorkerState):
    # Execute with LLM 
    messages = [
        SystemMessage(content=f"You are a coding assistant. Your overall goal is: {state['task_goal']}"),
        HumanMessage(content=f"Please implement this specific step: {state['task_description']}\nReturn ONLY the code.")
    ]
    response = llm.invoke(messages)
    
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    
    return {
        "generated_code": [response.content],
        "total_tokens": tokens
    }

# --- 4. Build Graphs ---

def build_sequential_graph():
    builder = StateGraph(SequentialState)
    builder.add_node("worker", sequential_worker)
    builder.add_edge(START, "worker")
    builder.add_conditional_edges("worker", sequential_router)
    return builder.compile()

def build_distributed_graph():
    builder = StateGraph(DistributedState)
    builder.add_node("parallel_worker", parallel_worker)
    # START -> conditional edge that maps out to workers
    builder.add_conditional_edges(START, distributed_dispatcher)
    # The Send API automatically routes back to END when all workers finish
    return builder.compile()

# --- 5. LangSmith Evaluator Boilerplate ---

def run_pytest_on_string(code_str: str) -> bool:
    # Dummy placeholder for your PyTest evaluator execution
    return True

def code_accuracy_evaluator(run, example):
    # Original LangSmith evaluator logic
    # (Assuming run.outputs contains the generated code list)
    generated_code = run.outputs.get("generated_code", [])
    success = all(run_pytest_on_string(c) for c in generated_code)
    return {"key": "code_correctness", "score": 1.0 if success else 0.0}

# --- 6. Profiling Harness ---

def profile_run(graph, state_input, name: str):
    print(f"\n{'='*40}")
    print(f"--- Profiling {name} ---")
    print(f"{'='*40}")
    
    start_time = time.time()
    
    result = graph.invoke(state_input)
        
    end_time = time.time()
    elapsed = end_time - start_time
    total_tokens = result.get("total_tokens", 0)
    
    print(f"Time Taken: {elapsed:.2f} seconds")
    print(f"Total Tokens Used: {total_tokens}")
    print(f"Generated {len(result.get('generated_code', []))} blocks of code.")
    
    return result

if __name__ == "__main__":
    if "GOOGLE_API_KEY" not in os.environ:
        print("WARNING: GOOGLE_API_KEY environment variable not set.")
        print("Please export it (e.g., `export GOOGLE_API_KEY='AIza...'`) before running to get real results.")
    
    # Example manual plan
    task_goal = "Build a simple math library with unit tests."
    plan = [
        "Write an addition function in python.",
        "Write a subtraction function in python.",
        "Write a multiplication function in python.",
        "Write a division function in python."
    ]
    
    print(f"Goal: {task_goal}")
    print(f"Tasks in Plan: {len(plan)}")
    
    # 1. Profile Sequential
    seq_graph = build_sequential_graph()
    seq_state = {"task_goal": task_goal, "plan": plan}
    
    # Uncomment to test
    profile_run(seq_graph, seq_state, "Sequential Plan")
    
    # 2. Profile Distributed
    dist_graph = build_distributed_graph()
    dist_state = {"task_goal": task_goal, "plan": plan}
    
    # Uncomment to test
    profile_run(dist_graph, dist_state, "Distributed Plan")