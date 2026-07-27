# PawPal+ (Final AI Project)

I am going to implement AI into the final version of Pawpal+ that I made in module two.

## AI Implementation:
1. I want to add an AI Agent that will completely help user to control the pet database as checking, planning, adjust, or give a recommendation. It will be presented as a chat box that user could give it a command, then it will break the user command into tokens, then defined the tasks, then plan what it needs to do, then execute.

## Limitations:
1. App has no memory so after I add the owner and pet, I have no way to comeback and adjust it. 
2. The website needs to contain the pages that support multiple purposes and button to direct between pages.

## Plan:
1. Create local database - one owner
2. Create different dashboard:
    a. To control Pet:
        i. Add the owner name, and pet, species, notes - so that if two pets can have the same activites and want a friend, they can go together.
        ii.Modify(even rename, edit-species, delete) the owner name, and pet, or species
            1. If delete, all the tasks related to the pet will be also deleted so make a Notice to the user.
    b. To control the Task:
        i.Add the task to the existed pet, included task name, duration, occurance (once a day, twice a day, three times a week) - give them choice to input the number of occurance and the options for day, week and month. For example, they can input 1 or 2 or 10 by themself, but they need to choose day, week or month. 
        ii.Add the note to the task, so that they can control and AI can look at the generate the schedule base on the foundation requirements and extra note.
    c. To control the Schedule - WILL TRY NOT FORCES
        i. Make it looks like google calendar go by week as user can track the pets tasks
        ii.
3. Add the function to adjust the tasks in control pet, control task and control schedule dashboard

## Action:
1. Extend the data model (foundation, no AI yet)
    a. Add notes field to Pet
    b. Add edit_pet (rename/species) and delete_task / edit_task methods — these don't exist at all yet
    c. Redesign frequency from the fixed "daily"/"weekly"/"as_needed" enum into frequency_count + frequency_unit (day/week/month) so "2x a day" is expressible
    d. Write pytest tests for each new method as you go, matching the existing TestAddPets-style class grouping
2. Build the "tool layer" for the agent
    a. Before touching any LLM code, wrap every model method (add_pet, edit_task, remove_pet, etc.) as a clean, well-documented function — these become the literal tool definitions the agent calls. Test them directly with plain function calls first, no AI involved.
3. Wire the AI agent (Claude API, tool-use)
    Take a user command string → let Claude pick a tool + arguments from Phase 3's set → execute → return a result. Build and test this as a standalone script (like main.py) before it touches Streamlit at all — much faster to debug.
4. Chat UI in Streamlit
    Add a chat box page that calls the Phase 4 agent and displays what it did (which tool ran, what changed).
5. Multi-page dashboards + week calendar view
    Last, because the calendar view is the biggest scheduler rewrite and dashboards are just UI wrapping around what already works by then
