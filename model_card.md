# Model Card
A project documentation with full reflection.

## What are the limitations or biases in your system?
### Limitations
- It has no ability about real world
- It can not import and export any documents (i.e. connect to Google Calendar and add the tasks directly there)
- Local run only, could not serve seperately for two owners. 
- No persistence across devices beyond the local JSON file - there's no cloud sync, so switching machines loses all pets/tasks.
- The scheduler only reasons about a single day window (`day_start`/`day_end`); it has no concept of a week, recurring conflicts across days, or the pet's actual calendar history.
- `species` and `notes` are free-text strings with no validation against a real taxonomy (`tool_add_pet` in `agent_tools.py:23` never checks that "crocodile" is a real pet a household would keep) - the system will happily register anything the user types.
- No undo/history log: once a `confirm=True` delete runs, the data is gone; there's no audit trail of who changed what and when.

### Biases
- The system is biased toward trusting whatever the user types as ground truth — since the tool layer's job is to prevent the *AI* from inventing data (per the Guardrail in the architecture diagram), but nothing stops the *user* from inventing implausible data (a "crocodile" pet, a 5-minute walk task with 200 repetitions/day) and having it treated identically to a real dog's feeding schedule.
- Priority handling assumes the user's stated priority (`high`/`medium`/`low`) reflects true urgency; there's no cross-check against task type (e.g., "medication" defaulting to high regardless of what the user labels it), so a mislabeled medical task could silently lose the scheduling fight against a correctly-labeled "walk."
- The window-filling scheduler assumes tasks are independent and interchangeable in time - it has no notion that some tasks (e.g., feeding right before a walk) might have order-dependencies a real owner would care about.

## Could your AI be misused, and how would you prevent that?
- Because `add_pet`/`add_task` accept arbitrary strings, the tool layer could be misused as a free-form note-dumping ground unrelated to pet care (spam text, unrelated reminders) since nothing in `agent_tools.py` scopes the content to plausible pet-care data.
- Prevention approach: we can't stop a user from hallucinating or acting in bad faith, but the tool layer can bound the *blast radius* cheaply, without needing real content moderation:
  - Cap `owner_name`, `pet_name`, and `species` to under 50 words each, and task `description`/`notes` to under 200 words — long enough for real pet-care detail, short enough to make spam-dumping or prompt-injection payloads impractical to hide in a field.
  - Cap the pet list at 500 pets total (per owner) — generous for any real household or even a small shelter, but it stops the JSON store from being used as unbounded free storage.
  - Add a species allowlist check in `tool_add_pet`: if the submitted species isn't a recognized companion-animal category, the tool still creates the pet (so a legitimate but unlisted pet isn't blocked outright) but the agent must relay an explicit warning back to the user rather than silently accepting it. Baseline allowlist, informed by common companion-animal legality:
    - Dogs and cats (note: first-generation hybrid cats, e.g. early-generation Savannahs, carry extra restrictions in some places and should still warn)
    - Small mammals: guinea pigs, mice, rats, chinchillas, Golden (Syrian) hamsters
    - Rabbits (domesticated)
    - Common cage birds: canaries, finches, budgies
    - Reptiles/fish: non-venomous snakes (king snakes, corn snakes) and common freshwater fish
    - Anything outside this list (the "crocodile" case) triggers a warning like "Lili's species isn't a typical registered pet - some jurisdictions restrict or ban keeping this animal; are you sure you want to proceed?" rather than a hard block, since the goal is nudging the user to notice, not gatekeeping edge cases like legitimately-permitted exotic pets.
  - These are all cheap, deterministic checks in the existing tool layer (no extra LLM call, no external API), so they add safety without adding hallucination surface of their own.
- Since everything is local JSON with no auth, anyone with file-system access to `pawpal_save.json` can read or edit another person's full pet/schedule data - fine for a single-user hobby project, but this would need real access control before being multi-tenant. (OUT OF PROJECT SCOPE)

## What surprised you while testing your AI's reliability?
- It was surprising how much reliability came from moving state changes *out* of the LLM entirely - the Guardrail split in the architecture (agent never mutates state directly, only calls deterministic functions) meant that once `agent_tools.py` and `pawpal_system.py` passed their pytest suite, most "AI reliability" issues actually turned out to be plain scheduling-logic bugs (the cursor-jump vs. window-filling issue), not LLM unpredictability.
- The remaining reliability risk lives entirely at the parsing boundary: the LLM still decides *which* tool to call and *how* to fill in parameters from natural language, so ambiguous input (e.g., "12pm everyday" vs. a one-off date) is where hallucinated or mis-mapped parameters would actually surface - that boundary is worth stress-testing more than the deterministic core.
- Confirmation-gated deletes (`confirm=False` first) turned out to be a cheap, effective safety net - it means even if the LLM misreads "delete Mochi" as more destructive than intended, the actual delete still requires a second explicit human-confirmed round trip.

## Describe your collaboration with AI during this project. Identify one instance when the AI gave a helpful suggestion and one instance where its suggestion was flawed or incorrect.
- AI is really useful as when it came to unfamiliar topics like create an app like this, it can point out many flaws that could happen with the project such as the user can type unpredictable or long input or spam and it can not check if the input is reliable that might not safe for them or system. It helps me to search the "common legal pet list" in order to generate a light boudaries to warn user if there pet is not included in the list. 

- A time that the AI agent suggested me flawly is asking me to build a cloud storage while the scope of the project is limited to local database, even the cloud storage provide more complex and flexible system, this does not go along with the my final project.   