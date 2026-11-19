# Measure Twice: input file format and rules for filling it in

This document is addressed to a language model that prepares a project file in a conversation with a person. The person does not read or edit the file: they load it into the application and see the result in its window. So the file must pass the check in full; the person will pass the check's remarks to you as they are.

## 1. What the file describes

- **Entity** — something that has a state. **Axis** — one independent attribute of an entity. An axis has a list of **values**.
- **Slice** — the values of all axes at one moment.
- **Transition kind** — a change of the value of one axis of one entity: it was "from", it became "to". Nothing else changes in a transition.
- **Transition** in a variant — a quadruple: transition kind, executor, instrument, scope.
- **Variant** — a linear chain of transitions. There are no forks: a fork is written as two variants.
- **Normalization** — the numbers. The **weight** of a transition = kind cost × scope coefficient × executor coefficient. The weight of a variant is the sum over its transitions.
- **Check** — a flag of a transition kind. **Check axis** — the axis that such a kind changes. **Skip** — a check axis that stayed on its initial value; a skip has a price.

The application knows nothing about the subject: all names are yours, in words, in the person's language. The numbers are assigned by the person; do not invent them silently — propose them and ask.

## 2. General rules

- One JSON file in UTF-8 encoding.
- A reference is a name written letter for letter the same as in the place where it is declared (case, spaces, accents and other special characters).
- Numbers are JSON numbers (`2`, `0.1`), not strings.
- The order in lists matters: everything is shown in that order, and the first value of an axis is the initial one.
- An optional field that is not needed is not written at all.

## 3. Sections of the file

| Field | Required | What it is |
|---|---|---|
| `format` | yes | Format number: `1` |
| `name` | yes | Project name |
| `description` | no | One or two sentences about the project |
| `existence_axis` | yes | `{"name": …, "absent": …}`: the name of the existence axis and the value meaning "does not exist". Always written, even if no entity has such an axis |
| `entities` | yes | Entities with axes and values |
| `kinds` | yes | Transition kinds |
| `executors` | yes | List of executor names |
| `instruments` | yes | List of instrument names |
| `scopes` | yes | List of scope names |
| `batch_scope` | yes | One of the scopes — the one that means "once for the whole batch" |
| `variant_params` | no | List of variant parameter names |
| `named_slices` | no | Named slices with conditions |
| `variants` | yes | Variants |
| `normalization` | yes | Normalization |

### 3.1. Entities: `entities`

```json
{"name": "Laundry", "axes": [
  {"name": "state", "values": ["dirty", "washed", "put away"]}
]}
```

- Entity names are not repeated; axis names are not repeated within an entity; values are not repeated within an axis.
- An axis has at least one value. **The first value is the initial one.**
- An axis is one independent attribute. If two attributes change independently, they are two axes, not one axis with a list of combinations.
- **Existence axis.** An entity that appears or disappears along the way gets an axis named as in `existence_axis.name`; among its values there must be `existence_axis.absent`. If this value is first, the entity does not exist at the start. While the entity does not exist, its other axes have no values. When it appears they get their initial values; when it disappears they lose them.
- `inherit` (optional, on an axis): `[["Entity", "axis"], …]` — where the axis takes its value from at the moment the entity appears: from the first source that has a value and whose value is among the values of this axis; otherwise the first value of the axis.

### 3.2. Transition kinds: `kinds`

```json
{"name": "Wash", "entity": "Laundry", "axis": "state",
 "from": "dirty", "to": "washed",
 "requires": [["Wash cycle", "presence", "present"]]}
```

| Field | Required | Rule |
|---|---|---|
| `name` | yes | Not repeated |
| `entity`, `axis` | yes | An existing entity and its axis |
| `from`, `to` | yes | Values of this axis; `from` is not equal to `to` |
| `requires` | no | Condition: a list of triples `[entity, axis, value]`. The transition is possible only if all triples hold in the current slice. A condition does not refer to the kind's own axis |
| `check` | no | `true` — the kind is a check; its axis becomes a check axis |
| `zero_weight` | no | `true` — the transition stays in the path but carries no labour |
| `zero_weight_note` | no | The reason; only together with `zero_weight: true`, non-empty text |
| `waiting` | no | The kind is waiting: how long, a number greater than zero. Only together with `waiting_unit` |
| `waiting_unit` | no | `"hours"` or `"days"`; a day counts as 24 hours. Only together with `waiting` |

Rules:

- A kind is a change of state, not an action of a particular person. Who does it and with what is written in the transition. Therefore **there cannot be two kinds with the same entity, axis, "from" and "to"**.
- **A kind must not duplicate a chain of other kinds on the same axis.** If there are "a → b" and "b → c", a kind "a → c" cannot exist: one shift would be written in two ways. If a short path is needed, remove the intermediate value or write both steps.
- The appearance of an entity is a kind on the existence axis from the "does not exist" value; the disappearance is a kind into that value.
- It is convenient to make a check axis of two values: "not checked", "checked". The initial one is "not checked".
- Check axes of different entities may have the same name: the price of a skip is written per pair "entity, axis".
- A waiting kind (with `waiting`) has no labour: its cost in `kind_costs` is omitted or `0`, it cannot be `check: true`, and executor and scope coefficients do not apply to it. Waiting is summed per path separately from labour.

### 3.3. Executors, instruments, scopes

Three lists of names, without repeats within a list.

- Executor — who does it: a person, a program, a device.
- Instrument — what it is done with. It is not part of the calculation, it only describes.
- Scope — what the action falls on: on each unit or once for the whole batch. `batch_scope` names the "per batch" scope.

### 3.4. Variant parameters: `variant_params`

A parameter is a named role that one of the executors fills in each variant. It is needed when a slice condition depends on who fills this role. If there is no such dependency, do not write the field.

```json
"variant_params": ["recipient"]
```

Then **every** variant has: `"params": {"recipient": "Person"}`.

### 3.5. Named slices: `named_slices`

A named slice is a moment at which skips are counted. It is set by a condition; in a variant it is the first slice where the condition holds.

```json
"named_slices": {
  "washed": {"any": [
    {"states": [["Laundry", "state", "washed"]]}
  ]}
}
```

- `any` — a non-empty list of groups; one satisfied group is enough ("or").
- In a group all rows hold together ("and"). Rows are `states`: triples `[entity, axis, value]`, and `params`: pairs `[variant parameter, executor]`. A group without rows is not allowed.
- The final slice always exists and is not written. The name `final` is taken.
- If the condition did not occur in a variant, the slice coincides with the final one.

### 3.6. Variants: `variants`

```json
{"code": "B", "title": "Quick wash", "side": "other", "task": "Wash the laundry", "calls": [
  ["Start the machine", "Person", "washing machine", "whole load"],
  ["Wash", "Machine", "washing machine", "whole load"]
]}
```

| Field | Required | Rule |
|---|---|---|
| `code` | yes | A short code, not repeated |
| `title` | yes | Title |
| `side` | no | `"own"` — own, `"other"` — someone else's; without the field — own |
| `task` | yes | The variant's task: non-empty text, compared as entered. Variants with the same task are compared with each other. A project saved in the database before the field became required opens without it: such a variant stays without a pair |
| `calls` | yes | Transitions in order: `[kind, executor, instrument, scope]`, all four from the reference lists |
| `params` | if `variant_params` exists | An executor for each parameter |
| `entities` | no | List of the variant's entities. Without the field — the entities touched by the transitions |
| `initial` | no | Deviations of the initial slice: `{"Entity": {"axis": "value"}}` |
| `out_of_comparison` | no | The reason why the variant is counted but does not go into the comparison; non-empty text |
| `steps` | no | The person's steps into which the transitions are split: `[{"text": …, "calls": …}, …]`. `text` — the step in the person's words, non-empty text; `calls` — how many transitions in a row from the variant's `calls` belong to it, an integer, 0 or more. `calls: 0` is allowed: a step without a transition. The sum of `calls` over the steps equals the number of the variant's transitions, otherwise the remark `steps cover N calls, the variant has M` |

The run of a variant is the main rule. A variant is executed step by step from the initial slice:

1. Initial slice: for each entity of the variant each axis is on its first value (taking `initial` into account); for an absent entity only the existence axis has a value.
2. For each transition: the current value of the kind's axis must equal its `from`; all `requires` triples must hold. Then the axis gets `to`.
3. The first step where this is not so is an error of the variant.

Before writing a variant, walk through it step by step yourself, keeping the slice in mind.

### 3.7. Normalization: `normalization`

| Field | Required | Rule |
|---|---|---|
| `kind_costs` | yes | `{kind: cost}` — for each kind without `zero_weight` and without `waiting`. For a kind with `zero_weight` or `waiting` the cost may be omitted; if written, only `0`. The cost of a kind without `zero_weight` is greater than zero |
| `executor_coefficients` | yes | `{executor: coefficient}` — for each executor. One whose labour is not counted (a program, a device) gets `0`. The coefficient is not less than zero |
| `scope_coefficients` | yes | `{scope: coefficient}` — for each scope. The coefficient is not less than zero |
| `axis_skip_prices` | yes | `{entity: {check axis: price}}` — for each check axis and only for them. The price is greater than zero |
| `batch_size` | no | The size of the batch for which the scope coefficients are given; a reference number |
| `labour_per_waiting_hour` | no | How much labour one hour of waiting is worth, in the cost unit. A number not less than zero; default `0`: waiting is shown but not added to labour. Above zero, the comparison adds "Labour + waiting" = labour + waiting hours × this number |
| `uncounted_errors` | no | `{group: [text, …]}` — errors that have no axis of their own; shown as a list, not counted |

- There must be no extra names: only those that are in the reference lists.
- The weight is counted per one unit. If a batch is 10 units, the usual pair of scope coefficients is: "each" — `1`, "per batch" — `0.1`.
- The unit of cost is chosen by the person; it is one for the whole project.

## 4. Work order

1. Find out from the person the process and the variants they want to compare; which of them are their own and which are someone else's; what task each variant solves. Do not go further without a task for each variant: ask the person for it.
2. Pick out entities and axes. Do not split too finely: an axis is needed if its value changes in at least one variant or stands in a condition.
3. Write the transition kinds; mark the checks.
4. Write the person's steps in their own words for each variant. Split each step into transitions and write `steps` next to `calls`. A step that gave no transition is not thrown away: write it with `calls: 0`.
5. Write the variants and run each one step by step. Set `task` for each variant — without it the file will not load. Variants with the same task are compared with each other; a variant with a unique task stays without a pair.
6. Agree the normalization numbers with the person.
7. Before handing over the file, show the person the chains as text: for each path its task, the steps in the person's words, and under each step its transitions; mark a step without a transition "no transition". Hand over the file only after the person agrees with the breakdown.
8. Check the file against the list in section 5.

## 5. Typical errors

The check gives its remarks in the language of the window; the names in them are as written in the file. The table retells the meaning of the remarks (the wording of the remarks is retold, except for those quoted in backticks). A file with incomplete normalization does not load.

| Error | What the check says | What to do |
|---|---|---|
| A name in a reference differs from the declared one | unknown entity, axis, value, kind, executor, instrument or scope — with the place | Bring to one spelling |
| A name is repeated | duplicate — with the name | Rename or remove |
| A kind has `from` equal to `to` | "from" equals "to" | This is not a transition; remove |
| A kind's condition on its own axis | condition on the kind's own axis | The condition is already expressed in `from` |
| Two kinds with one state change | the same quadruple | Keep one; the difference is in the executor and instrument of the transition |
| A kind duplicates a chain of others | the kind decomposes — with the chain | Remove the short kind or the intermediate value |
| A transition not from the current value | variant, transition number: the axis has one value, another was expected | A step is missed or swapped |
| A condition is not met | variant, transition number: condition not met | Add the missing step earlier |
| A transition on an axis of an entity that is not in the variant | the entity is not part of the variant | Add it to `entities` or remove the field |
| The entity does not exist yet, and its axis is changed | the axis has no value, the "from" was expected | The appearance transition first |
| The existence axis has no "does not exist" value | the existence axis lacks this value | Add the value |
| `batch_scope` is not from the list of scopes | the "per batch" scope is not found | Name an existing scope |
| A variant has no parameter set | variant parameter not set | Set `params` for every parameter |
| A number is missing in normalization | kind without a cost; executor or scope without a coefficient; check axis without a price | Add the number |
| An extra name in normalization | cost of an unknown kind; price of an axis that is not a check axis | Remove |
| A kind has `zero_weight`, but the cost is not 0 | weight is 0 but a cost is given | Set `0` |
| A kind without `zero_weight` costs 0 | a kind with labour costs 0 | Give the labour, or mark the kind `zero_weight` if it is waiting or work without labour |
| `waiting` without `waiting_unit`, or the other way round; waiting not above 0; a unit other than hours or days | `kind X: waiting needs a number above 0 and the unit hours or days` | Write both fields: a number above 0 and `"hours"` or `"days"` |
| A waiting kind is marked `check` | a waiting kind cannot be a check | Remove `check` or `waiting` |
| A waiting kind has a cost other than 0 | the kind is a waiting kind, its cost must be 0 or absent | Remove the cost or set `0` |
| A number written as a string | a number was expected | Remove the quotes |
| A negative number; skip price 0 | number out of the allowed range | Costs and coefficients are not less than zero, the skip price is greater than zero |
| No `task` | `variant X: task is required` | Write the variant's task |
| `task` is empty or not text | `variant X: task must be a text` | Write the task as non-empty text |
| `steps` is not a list | `variant X: steps must be a list` | Write a list of steps or remove the field |
| A step's `text` is empty or not text | `variant X, step N: text must be a text` | Write the step as non-empty text |
| A step's `calls` is not an integer or is less than zero | `variant X, step N: calls must be an integer, 0 or more` | Write an integer from 0; a step without a transition is `0` |
| The sum of the steps' `calls` is not equal to the number of transitions | `variant X: steps cover N calls, the variant has M` | Compare the steps with the variant's `calls`: each transition in exactly one step |
| A slice is named `final` | the name is taken | Rename |

## 6. A full example

The subject is washing one load of laundry, three variants. (Here the names are in English because this document is in English; in a real project all names, titles, tasks and step texts are written in the person's language.)

```json
{
  "format": 1,
  "name": "Laundry washing",
  "description": "Three ways to wash one load of laundry.",
  "existence_axis": {"name": "presence", "absent": "absent"},
  "entities": [
    {"name": "Laundry", "axes": [
      {"name": "state", "values": ["dirty", "washed", "hung", "dry", "put away"]},
      {"name": "pockets", "values": ["not checked", "checked"]},
      {"name": "colors", "values": ["not sorted", "sorted"]}
    ]},
    {"name": "Wash cycle", "axes": [
      {"name": "presence", "values": ["absent", "present"]}
    ]}
  ],
  "kinds": [
    {"name": "Check pockets", "entity": "Laundry", "axis": "pockets",
     "from": "not checked", "to": "checked", "check": true},
    {"name": "Sort by colors", "entity": "Laundry", "axis": "colors",
     "from": "not sorted", "to": "sorted", "check": true},
    {"name": "Start the machine", "entity": "Wash cycle", "axis": "presence",
     "from": "absent", "to": "present"},
    {"name": "Wash", "entity": "Laundry", "axis": "state",
     "from": "dirty", "to": "washed",
     "requires": [["Wash cycle", "presence", "present"]]},
    {"name": "Hang", "entity": "Laundry", "axis": "state",
     "from": "washed", "to": "hung"},
    {"name": "Wait for drying", "entity": "Laundry", "axis": "state",
     "from": "hung", "to": "dry",
     "zero_weight": true, "zero_weight_note": "waiting, no labour"},
    {"name": "Put in the closet", "entity": "Laundry", "axis": "state",
     "from": "dry", "to": "put away"}
  ],
  "executors": ["Person", "Machine"],
  "instruments": ["hands", "washing machine", "drying rack"],
  "scopes": ["each item", "whole load"],
  "batch_scope": "whole load",
  "named_slices": {
    "washed": {"any": [{"states": [["Laundry", "state", "washed"]]}]}
  },
  "variants": [
    {"code": "A", "title": "Careful wash", "side": "own", "task": "Wash the laundry", "calls": [
      ["Check pockets", "Person", "hands", "each item"],
      ["Sort by colors", "Person", "hands", "each item"],
      ["Start the machine", "Person", "washing machine", "whole load"],
      ["Wash", "Machine", "washing machine", "whole load"],
      ["Hang", "Person", "drying rack", "each item"],
      ["Wait for drying", "Person", "drying rack", "whole load"],
      ["Put in the closet", "Person", "hands", "each item"]
    ],
    "steps": [
      {"text": "Get the detergent out", "calls": 0},
      {"text": "Check the pockets", "calls": 1},
      {"text": "Sort by colors", "calls": 1},
      {"text": "Load the laundry and start the machine", "calls": 2},
      {"text": "Hang the laundry", "calls": 1},
      {"text": "Wait until it is dry", "calls": 1},
      {"text": "Put it in the closet", "calls": 1}
    ]},
    {"code": "B", "title": "Quick wash", "side": "other", "task": "Wash the laundry", "calls": [
      ["Start the machine", "Person", "washing machine", "whole load"],
      ["Wash", "Machine", "washing machine", "whole load"],
      ["Hang", "Person", "drying rack", "each item"],
      ["Wait for drying", "Person", "drying rack", "whole load"],
      ["Put in the closet", "Person", "hands", "each item"]
    ],
    "steps": [
      {"text": "Load the laundry and start the machine", "calls": 2},
      {"text": "Hang the laundry", "calls": 1},
      {"text": "Wait until it is dry", "calls": 1},
      {"text": "Put it in the closet", "calls": 1}
    ]},
    {"code": "C", "title": "Wash with a pocket check", "side": "other", "task": "Wash the laundry", "calls": [
      ["Check pockets", "Person", "hands", "each item"],
      ["Start the machine", "Person", "washing machine", "whole load"],
      ["Wash", "Machine", "washing machine", "whole load"],
      ["Hang", "Person", "drying rack", "each item"],
      ["Wait for drying", "Person", "drying rack", "whole load"],
      ["Put in the closet", "Person", "hands", "each item"]
    ],
    "steps": [
      {"text": "Check the pockets", "calls": 1},
      {"text": "Load the laundry and start the machine", "calls": 2},
      {"text": "Hang the laundry", "calls": 1},
      {"text": "Wait until it is dry", "calls": 1},
      {"text": "Put it in the closet", "calls": 1}
    ]}
  ],
  "normalization": {
    "batch_size": 10,
    "kind_costs": {
      "Check pockets": 2,
      "Sort by colors": 3,
      "Start the machine": 4,
      "Wash": 1,
      "Hang": 2,
      "Wait for drying": 0,
      "Put in the closet": 1
    },
    "executor_coefficients": {"Person": 1, "Machine": 0},
    "scope_coefficients": {"each item": 1, "whole load": 0.1},
    "axis_skip_prices": {"Laundry": {"pockets": 5, "colors": 3}},
    "uncounted_errors": {"Outside the model": ["the detergent ran out"]}
  }
}
```

What can be seen in the example:

- "Wash cycle" does not exist at the start: the first value of its existence axis is "absent". "Wash" requires it to be present.
- "Wash" is done by the machine with coefficient 0: the step is in the path, but it has no weight.
- "Wait for drying" — weight 0 with a reason; `kind_costs` has `0` (it could have been left out).
- "Start the machine" — once per load: 4 × 0.1 × 1 = 0.4.

The result for this file:

| Variant | Weight | The "washed" slice occurs after step | Skips on it | Sum | Skips on the final | Sum |
|---|---|---|---|---|---|---|
| A Careful wash | 8.4 | 4 | none | 0 | none | 0 |
| B Quick wash | 3.4 | 2 | pockets, colors | 8 | pockets, colors | 8 |
| C Wash with a pocket check | 5.4 | 3 | colors | 3 | colors | 3 |

Variant "B" is the lightest and has the largest sum of skips: the weight and the skips are shown side by side and are not converted into each other.
