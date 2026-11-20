# Measure Twice: user guide

Measure Twice compares ways of doing one job: how many steps each way has, how much work it
takes, who does it, and how much risk is left. You describe the ways, the program counts.

## Start

From the build, unpack the archive and run `measure_twice/measure_twice`. From source, run
`python -m measure_twice` in the project folder. The window opens with the list of your
projects at the top. At the first start it already holds one example.

## A new project

Press **+ New ▾** in the top row, or **✦ Add with AI** next to it.

### With AI

1. Press **✦ Add with AI**. The window **Add a process with AI** opens.
2. In step 1 describe the job in one or two sentences, for example "replace a leaking tap in
   a kitchen". Press **Copy prompt**.
3. Paste the prompt into the chat of your AI assistant. Read its answer and agree on the ways,
   the steps and who does what.
4. Come back, press **Next step**, copy the next prompt and give it to the same chat. Repeat
   for each step.
5. The last prompt makes the AI write a file. Copy its whole answer, paste it under **Paste
   the AI’s answer** and press **Load file**.
6. If the program finds problems, it lists them in the last step. Copy that prompt into the
   same chat, paste the corrected answer and press **Load file** again.

If you already have the AI's answer, use **+ New ▾**, then **Paste AI answer…**, paste the
text and press **Load**.

### Empty, example, from file

Under **+ New ▾**:

- **Empty** makes a project with nothing in it. Fill it on the tabs, start with
  **Dictionary**.
- **Example** adds a ready project to look at and to try.
- **From file…** loads a project from a `.json` file.

## The tabs

- **Dictionary**: the words of the project. Entities and their states (a tap: installed,
  leaking, replaced), kinds of steps, executors, instruments, scopes. Each list has a
  button to add a row.
- **Normalization & variants**: the numbers. The cost of each kind of step, the coefficients
  of executors and scopes, the price of a skipped check. Variants are the ways to compare.
- **Step chains**: the steps of each way, one after another. Press **New** to add a way;
  for every step choose the kind, the executor, the instrument and the scope from the lists.
- **Comparison**: the result. See below.

A project is usually filled in this order: **Dictionary**, **Step chains**,
**Normalization & variants**, then **Comparison**.

## The table and the comparison

On **Comparison** the ways are in a table grouped by task. Ours come first, then theirs.
Lower labour is cheaper, but the risk left is counted separately: a cheap way may leave
checks undone. Click a row to see its steps; **Back to table** returns.

- **Side:** shows all ways or one side. **All** shows everything.
- **Compare steps** puts the steps of the chosen ways next to each other.
- **Copy table** copies the table to paste into a sheet or a message.

## Saving and export

Nothing needs saving: every edit is written at once, and the projects are there at the next
start. To make a file to send or to keep, open **More ▾**:

- **Export to file…** writes the project as a `.json` file.
- **Duplicate** makes a copy of the open project.
- **Replace from file…** loads a file over the open project.
- **Delete…** removes the project; it cannot be undone.

On **Comparison**, **Export table (Markdown)** and **Export table (CSV)** write the table,
and **Report (PDF)…** makes a report of the pages and ways you choose.

## Language

The button at the right end of the top row shows the language: **EN ▾**, **RU ▾** or
**EL ▾**. Choose English, Русский or Ελληνικά in its list. The window changes at once; the
project, the tab and the size stay. The user guide is in English and Russian; for Greek the
English one is shown.

The guide opens from **More ▾**, **User guide**.
