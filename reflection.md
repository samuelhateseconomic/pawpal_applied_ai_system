# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
At first, I follow the three core actions: 
1. add/edit pets
2. add/edit tasks
3. Schedule a Plan
to build a three classes following as:
1. Pet
2. Task
3. Daily Schedule
And my UML design looks like after I reinforced it with Claude code and visualize it through mermaid.live:
classDiagram
    class Pet {
        -name: string
        -breed: string
        -age: int
        -owner_name: string
        -available_start_time: str
        -available_end_time: str
        +add_pet(name, breed, age, owner_name, start, end) void
        +edit_pet(name, breed, age, owner_name, start, end) void
        +get_availability() tuple
    }
    
    class Task {
        -task_id: int
        -name: string
        -duration_min: int
        -priority: str (HIGH/MEDIUM/LOW)
        -category: str
        +add_task(name, duration, priority, category) int
        +edit_task(task_id, name, duration, priority, category) void
        +get_priority() str
    }
    
    class DailySchedule {
        -pet: Pet
        -tasks: list[Task]
        -scheduled_items: list[dict]
        -date: str
        +generate_schedule(pet, tasks) list
        +get_schedule() list[dict]
        +explain_reasoning() str
    }
    
    DailySchedule --> Pet: uses constraints from
    DailySchedule --> Task: arranges

- What classes did you include, and what responsibilities did you assign to each?
I believe my UML on top does included the answer for this question.

**b. Design changes**

- Did your design change during implementation?
Yes, it does before the implementation because I see that the design is overcomplicated compare to the version from the app.py and we do not even have the owner class.
- If yes, describe at least one change and why you made it.
There are few changes: 
1. Adding class: Owner
2. Deleting extra functions that are not mentioned in the app.py
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
Constraints that my schedule consider are:
1. Only pending tasks are scheduled
2. User exact time input - user can choose what they want to do first by adding the exact time (HH:MM)
3. Priority order (high -> medium -> low) - shortest-first within the same tier - which maximizes the number of tasks that fit before it runs out.
- How did you decide which constraints mattered most?
1. It is obviously that the completed tasks do not need to be scheduled. Besides, even though the user has the priority order, they can have their personal reason to do what they want so the user exact time is mattered the most.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.

**Simplicity vs. Correctness: cursor-jump vs. window-filling**

The first version of `assign_times()` used a single moving cursor. It placed tasks one after another from `day_start`, and when it hit a pre-set anchor task (e.g. Vet visit at 10:00), it jumped the cursor to that anchor's end time. The logic was simple — about 8 lines.

The problem: the cursor jumped *past* the anchor without looking back. Any floating task placed before the anchor consumed the 09:00–10:00 window correctly, but once the cursor jumped to 11:00, all remaining tasks — including low-priority ones that could have fit in the gap — landed after 11:00. The gap was wasted.

The fix required replacing the single cursor with a **window-filling algorithm**:
1. Anchor tasks divide the day into named time windows: `[09:00–10:00]`, `[11:00–21:00]`, etc.
2. Each floating task is placed in the **first window where it fits**, in priority+shortest-first order.
3. A separate cursor tracks the fill position inside each window independently.

This added roughly 20 lines and a new data structure (`windows: list[tuple[int, int]]`), plus explicit type annotations to keep the type checker happy.

- Why is that tradeoff reasonable for this scenario?

For a pet owner managing a real day, unused gaps matter. If a vet appointment is at 10:00, the owner should be able to fit Feeding and Medication into the 09:00–10:00 window automatically — not have them pushed to 11:00 just because the cursor jumped. The added complexity is justified because the simpler version silently produced a worse schedule with no warning. The window-filling version is still deterministic and easy to trace: each task lands in the earliest slot that fits its duration, respecting both priority and user-set anchors.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
In this project, I use AI for brainstorming, and coding with me.
- What kinds of prompts or questions were most helpful?
The most helpful prompt is "Help me write the test to test all the behaviors from happy paths to edge paths where everything can go wrong of the app."
**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
I did when AI tried to fix the function with the certain timeline that eliminate the user right to add their refered time.

- How did you evaluate or verify what the AI suggested?
I read all the code before it changed and I think understand the skeleton of the project help alot to keep up with the AI flow.
---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
1. Add Pets
2. Add Tasks with Time
3. Schedule Tasks
4. Explain the Schedule

- Why were these tests important?
Because these are all fundamental functions of the test, the app could not run if the base can not provide a strong foundation.

**b. Confidence**

- How confident are you that your scheduler works correctly?
5 stars
- What edge cases would you test next if you had more time?
1. Input Validation
2. Cleaning the task if it is done - MAYBE

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?
I believe the revise part is the most satisfied.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?
I think I can try to add the function where two pets can be considered to have the activity together.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
I have to pay attention to detail because AI can mess with it if I pay no attention and it took me a whole hour to fix it as the session_state part as I thought it was already fixed.
