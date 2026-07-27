# PawPal+ AI System Architecture & Agent Workflow

This document outlines the design, tool integration layer, and decision flow for the AI Agent implementation in **PawPal+**. The architecture enforces a **Single-Agent Function-Calling Pattern**, utilizing deterministic Python functions (`pawpal_system.py`) for business logic and conflict calculations while keeping the LLM focused on intent parsing and conversation.

---

## 0. System Overview

PawPal+ doesn't use a document retriever (no RAG), so the "retriever" role is filled by the **Tool Layer**, which fetches/executes deterministic ground truth from the pet-scheduling engine instead of an LLM guess. The **evaluator** role is filled by the **Guardrail + Conflict Detector**, which checks the agent's requested action against required-parameter rules and scheduling conflicts before anything is treated as final. The **tester** role is split between the automated **pytest suite** (`tests/`) and the **human user**, who reviews every natural-language response before trusting or acting on it.

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    %% Nodes
    User([User / Owner]) 
    UI[ Streamlit Chat Interface]
    Agent[Gemini AI Agent]
    
    subgraph Guardrails ["Agent Guardrail Layer"]
        CheckInfo{Required Parameters<br/>Present?}
        AskClarification[Ask User for Missing Information]
    end

    subgraph ToolLayer ["Python Tool Layer (agent_tools.py)"]
        ExecTool[Execute Function Call]
    end

    subgraph CoreEngine ["PawPal Engine (pawpal_system.py)"]
        OwnerPetModel[Owner & Pet Models]
        SchedulerEngine[Scheduler & Time Allocator]
        ConflictDetector[Conflict Detection System]
        Storage[(pawpal_save.json)]
    end

    %% Flow Connections
    User -->|Natural Language Input| UI
    UI -->|Prompt + Context| Agent
    Agent --> CheckInfo

    CheckInfo -- "No (Missing Duration, Priority, etc.)" --> AskClarification
    AskClarification -->|Natural Prompt| UI

    CheckInfo -- "Yes (Complete Schema)" --> ExecTool
    ExecTool --> OwnerPetModel
    OwnerPetModel --> Storage
    ExecTool --> SchedulerEngine
    SchedulerEngine --> ConflictDetector

    ConflictDetector -->|Returns Status & Warnings| ExecTool
    ExecTool -->|Structured JSON Result| Agent
    Agent -->|Friendly natural language response| UI
```

## 2. Sequence Diagram: Interaction & Conflict flow

```
sequenceDiagram
    autonumber
    actor User as User
    participant UI as Streamlit UI
    participant LLM as Gemini Agent
    participant Tool as Tool Layer
    participant System as pawpal_system.py

    --- SCENARIO 1: INCOMPLETE COMMAND ---
    Note over User, System: Scenario 1: Ambiguous / Incomplete Request
    User->>UI: "Add a walk for Mochi"
    UI->>LLM: Send message history & prompt
    Note over LLM: Validates required params for add_task tool.<br/>Missing: duration_minutes, priority
    LLM-->>UI: "How long is the walk (min), and what priority should it have?"
    UI-->>User: Display clarification request

    --- SCENARIO 2: COMPLETE COMMAND WITH CONFLICT ---
    Note over User, System: Scenario 2: Execution & Conflict Detection
    User->>UI: "30 minutes, high priority, fixed at 09:00 AM"
    UI->>LLM: Send context update
    LLM->>Tool: tool_add_task(pet_name="Mochi", title="Walk", duration=30, priority="high", start_time="09:00")
    Tool->>System: pet.add_task(...)
    Tool->>System: Scheduler(tasks).schedule()
    System-->>Tool: ScheduleResult(tasks, conflicts=["WARNING [SAME PET: Mochi] 'Walk' (09:00) overlaps 'Grooming' (09:00)"])
    Tool-->>LLM: {"status": "conflict_warning", "conflicts": [...]}
    LLM-->>UI: "I added 'Walk' at 9:00 AM, but Mochi already has 'Grooming' scheduled then. Should we move one?"
    UI-->>User: Display final response & conflict notice
```
## 3.Tool Maping Matrix
The agent operates strictly through function calls defined in agent_tools.py, which wrap the methods of pawpal_system.py:

Agent Tool Function	- Backend Method - Description - Guardrail / Exception Behavior
1. tool_add_pet - Owner.add_pet() - Registers a new pet - Checks if pet already exists.
2. tool_edit_pet - Owner.edit_pet() - Edits species, notes, or renames pet	 - Prevents duplicate pet name collisions.
3. tool_add_task - Pet.add_task() - Appends task to a pet - Requires duration & priority before execution.
4. tool_edit_task - Pet.edit_task() - Modifies existing task fields - Fails gracefully if task title is not found.
5. tool_delete_task - Pet.delete_task()	- Removes task by title	- Asks confirmation if deleting triggers orphaned dependencies.
6. tool_generate_schedule	- Scheduler.schedule() - Builds day plan & checks window - Triggers conflict reporting if budget is exceeded or overlaps occur.
7. tool_check_slots - Scheduler.find_available_slots() - Finds open time blocks - Returns available (start, end) tuples for a given duration.

## 4. System Prompt Guardrail Specifications

Strict Non-Assumption Rule: 
1. The model must never invent missing function parameters (e.g., duration, start time, or priority). If incomplete, it must pause and ask the user.

2. ransparent Error Propagation: Any output returned by Scheduler.detect_conflicts() must be directly explained to the user in human-readable terms.

3. Deterministic State Synchronization: All tool state modifications must trigger a call to save_owner() to guarantee data persistence.