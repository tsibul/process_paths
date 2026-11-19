# Measure Twice: six prompts for an AI chat

The person talks to an AI chat (ChatGPT, Gemini) in six steps and only copies the prompts below.
Each step is one prompt; the person adds at most a sentence or two, then answers the AI's
"Points to check" with "yes" or a correction in words. The format is needed only at step 5.
Step 6 is built by the program when it refuses the file; it is used again until the file loads.

## Prompt 1. Task

Use it first, in a new chat. Replace {task} with one or two sentences about the task.

```text
We will prepare a file for Measure Twice, a program that compares ways of doing one task by labour.
We go in six steps; I will give you a prompt for each. Rules for the whole conversation:
- Do each step yourself. Do not stop to ask me questions. Where unsure, take the likely answer.
- End every answer with "Points to check": 2-4 numbered doubtful places. I answer "yes" or
  correct them in words.
- Propose numbers yourself and mark the doubtful ones.
- Use the language of my task for all text and names.
- Write no file until step 5.

Step 1. Task.
My task: {task}

Give the task one short name; all ways share it. List the ways to do it that you understood
from my words: a short title, one line on what is done, and "own" (mine) or "other"
(someone else's). Then add the usual ways I did not mention: only ways that really solve the
task, always "other". End the title of each added way with "(added)" and keep it in every
step and in the file. In "Points to check" name each added way and ask which ways are missing
or extra.
```

## Prompt 2. Steps

Use it when the list of ways is agreed.

```text
Step 2. Steps.
Write every agreed way out step by step. I give you no steps: write them yourself, as the work
is really done.
- Include the routine steps: prepare (shut off the water or power), check the result,
  clean up.
- One step is one action, in plain words. Say who does it.
- A way that hands the work to someone (a hired worker, a service) lists that worker's steps.
- If two ways reach the same result differently, say which part each step works on
  (replace the washer, tighten the nut, tape the thread), not just "fix it".
- A way without a check gets no step for it, not even "no check is made".
- Mark each step where the person only waits (for a plumber, for a delivery) and give a rough
  duration.
- In "Points to check" name, in one point, the steps you added that are not in my words.
Show a numbered list per way. No file format yet.
End with "Points to check": the 2-4 steps you are least sure of.
```

## Prompt 3. Same actions and checks

Use it when the steps are agreed.

```text
Step 3. Same actions and checks.
Go over the steps of all ways together.
1. The same action gets the same name in every way, word for word.
2. For each action say what it changes: one attribute of one thing, from one state to
   another. Example: "Replace the washer: Washer, worn -> new".
3. Two actions must never make the same change. Different ways to one result act on different
   parts: Washer, worn -> new; Nut, loose -> tight.
4. An action with no change of its own gets a new attribute (Floor: wet -> dry). Never hang it
   on another thing's change. Only work without labour is "no labour".
5. Mark the checks: a check confirms the result after an action, and skipping it has a price.
   If my words call an action a check, it is a check. Otherwise finding the cause of a fault
   is an ordinary action. A check changes the thing it checks:
   "Test for leaks: Tap, leak not tested -> tested". A way without a check gets no step for
   it; the thing still has the check attribute, so the skip shows.
6. Say what appears or disappears along the way (a bucket put under, a visit booked).
7. Waiting for someone is its own kind of action: not a check, not labour. It still changes an
   attribute of its own (Plumber visit: booked -> done).
Then run each way: every action starts from the state the previous one left. Fix any that
does not.
Show a table: action | thing | attribute | from -> to | check. Then each way as action names.
End with "Points to check".
```

## Prompt 4. Who and how much

Use it when the actions and checks are agreed.

```text
Step 4. Who and how much.
1. List the executors: who or what does the actions.
2. Give each a coefficient: how much of their labour counts, 1 for the main person.
   Coefficient 0 only for a machine or program that works by itself. Never 0 for a person,
   a hired one included. Put every coefficient 0 into "Points to check".
3. Give each action a labour cost in one unit for the whole project (minutes or points).
   Paying is not labour: no action for it. Waiting for someone is an action with a duration
   in hours or days, not a cost or weight: mark each with "?". A short wait with no duration
   needed (water draining) costs 0.
4. Say whether each action is done once for the whole job or for each unit; if per unit, how
   many units a batch has.
5. For each check give the price of skipping it, more than 0. Never add it to labour.
6. Show the total of each way: sum of cost x executor coefficient x scope coefficient.
   If steps not in my words change a way's total noticeably, say so in "Points to check".
Mark doubtful numbers with "?".
End with "Points to check".
```

## Prompt 5. File

Use it when the executors and numbers are agreed.

```text
Step 5. File.
Write what we agreed as one Measure Twice file: JSON, whole, in one code block, in my language.
Use only the actions agreed at steps 2-4; add no preparation (get or put away tools) I did not
name. First run each variant through the axes yourself. Then "Points to check":
choices you made.

FORMAT
A reference is the declared name letter for letter. Numbers are JSON numbers. Order matters.
No name repeats in one list. Leave out unneeded optional fields.

Top level (* required): format* = 1; name*; existence_axis* {"name","absent"};
entities*; kinds*; executors*, instruments*, scopes* - lists of names; batch_scope* - the
scope "once per batch"; named_slices; variants*; normalization*.

entities: {"name", "axes": [{"name", "values": [...]}]}. The FIRST value is the initial one.
An axis is one independent attribute. A thing that appears or disappears gets an axis named
existence_axis.name, first value existence_axis.absent; while absent, its other axes have no
value. No ordinary axis has this name.

kinds: {"name", "entity", "axis", "from", "to"} plus optional:
requires [[entity, axis, value], ...] - must hold before; never the kind's own entity and
axis: "from" already says it;
check: true - confirms the result of an action; on an axis of the thing checked;
zero_weight: true with zero_weight_note - a step with no labour (draining).
waiting: number > 0 with waiting_unit "hours"|"days" - waiting for someone: no cost, no check.
Paying is not labour: no kind for it.
from != to. No two kinds with the same entity, axis, from and to. No kind duplicating a chain
(a->b, b->c, so no a->c). An action with no axis of its own gets a new axis.

named_slices (optional): {"name": {"any": [{"states": [[entity, axis, value], ...]}]}} -
skips are counted when one group first holds. "final" is taken.

variants: {"code", "title", "side": "own"|"other", "task", "calls", "steps"}. Ways with the
same task text are compared. calls - [kind, executor, instrument, scope]; each starts from the
value the previous one left; all requires hold. A way without a check has no call for it.
steps - [{"text": step in my words, "calls": how many calls in a row}]; calls may be 0; the
sum equals the number of calls.

normalization: kind_costs {kind: cost} for every kind (zero_weight, waiting: 0 or left out);
executor_coefficients {executor: k} for every executor, 0 only for a machine or program;
scope_coefficients {scope: k} for every scope (per unit 1, per batch 1/batch size);
axis_skip_prices {entity: {check axis: price > 0}} for every check axis and only those, never
added to labour; batch_size optional; leave out labour_per_waiting_hour: I set it. No negative numbers. No extra names.

EXAMPLE
{"format": 1, "name": "Unblock a sink",
 "existence_axis": {"name": "exists", "absent": "no"},
 "entities": [
  {"name": "Pipe", "axes": [{"name": "clog", "values": ["blocked", "cleared"]}]},
  {"name": "Trap", "axes": [{"name": "inside", "values": ["dirty", "clean"]}]},
  {"name": "Bucket", "axes": [{"name": "exists", "values": ["no", "yes"]}]},
  {"name": "Visit", "axes": [{"name": "arrival", "values": ["not here", "here"]}]},
  {"name": "Sink", "axes": [{"name": "drain test", "values": ["not tested", "tested"]}]}],
 "kinds": [
  {"name": "Plunge", "entity": "Pipe", "axis": "clog", "from": "blocked", "to": "cleared"},
  {"name": "Put a bucket under", "entity": "Bucket", "axis": "exists", "from": "no", "to": "yes"},
  {"name": "Wait for the plumber", "entity": "Visit", "axis": "arrival",
   "from": "not here", "to": "here", "waiting": 2, "waiting_unit": "days"},
  {"name": "Clean the trap", "entity": "Trap", "axis": "inside", "from": "dirty",
   "to": "clean", "requires": [["Bucket", "exists", "yes"]]},
  {"name": "Test the drain", "entity": "Sink", "axis": "drain test", "from": "not tested",
   "to": "tested", "check": true}],
 "executors": ["Owner", "Plumber"],
 "instruments": ["hands", "plunger", "bucket", "wrench"],
 "scopes": ["job"], "batch_scope": "job",
 "variants": [
  {"code": "A", "title": "Plunger", "side": "own", "task": "Unblock the sink", "calls": [
    ["Plunge", "Owner", "plunger", "job"],
    ["Test the drain", "Owner", "hands", "job"]],
   "steps": [{"text": "Plunge the sink", "calls": 1},
    {"text": "Run the tap, watch the drain", "calls": 1}]},
  {"code": "B", "title": "Plumber", "side": "other",
   "task": "Unblock the sink", "calls": [
    ["Wait for the plumber", "Owner", "hands", "job"],
    ["Put a bucket under", "Owner", "bucket", "job"],
    ["Clean the trap", "Plumber", "wrench", "job"]],
   "steps": [{"text": "Wait for the plumber", "calls": 1},
    {"text": "Put a bucket under", "calls": 1},
    {"text": "The plumber cleans the trap", "calls": 1}]}],
 "normalization": {
  "kind_costs": {"Plunge": 3, "Put a bucket under": 1, "Clean the trap": 8, "Test the drain": 1},
  "executor_coefficients": {"Owner": 1, "Plumber": 0.8},
  "scope_coefficients": {"job": 1},
  "axis_skip_prices": {"Sink": {"drain test": 5}}}}
```

## Prompt 6. Remarks

The program builds this prompt when it refuses the file; the person only pastes it.

```text
Step 6. Remarks.
The program refused the file. Its remarks:
{remarks}

Fix every remark. Then check the whole file again against the step 5 format, not only the
places named: remarks may come in portions. Run each variant through the axes again: every
call starts from the value the previous one left. Keep everything we agreed; change only what
the fix needs, and say in one line per remark what you changed.
Give the whole file again in one code block, not a part of it.
End with "Points to check" only if a fix changed something we agreed.
```
