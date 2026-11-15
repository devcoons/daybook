# Usage

When the user asks how to use this workspace, answer with the matching entry. Do not add steps that this file does not list. Reply in English unless they explicitly asked for another language.

These entries are about this notebook. A question about the user's actual work (a project, a person, a file they already filed) is not a usage question.

## What is this?

Match: what is this, how does this work, what is a workstream, help, usage

This workspace is Daybook, a notebook of workstreams. A workstream is one ongoing topic. It holds a summary, the open tracker, dated notes, and any files or links you attach. Notes are the history. The tracker is what is still open.

You can write to me in any language. I keep the notes in English, and I answer in English unless you ask for another language.

## How do I create a workstream?

Match: create a workstream, new workstream, set-workstream, /set-workstream

Send `/set-workstream` and a title. A short description is optional.

Example: `/set-workstream SharePoint Storage Issue` — quota and permissions with IT.

That creates the workstream. It does not add a note. If that title already exists, I will ask before changing it.

## How do I add a note?

Match: add a note, file a note, /add-note, save a note

Send `/add-note` and the raw text, in any language.

I file it under the workstream you name. If you do not name one and only one workstream fits, I file it there. If it is unclear, I ask, including the option to start a new workstream. I translate the note into English, keep names and links as you wrote them, and tell you where it went. If I picked the wrong workstream, name the right one and I will move it.

## How do I find a note?

Match: find a note, search notes, /get-note, where did I write

Send `/get-note` and the words you remember. I search titles, notes, and resource names, newest first. I do not open attached files unless you ask me to use one.

## How do I see my workstreams?

Match: list workstreams, see my workstreams, /get-workstreams, what workstreams

Send `/get-workstreams`. You get each active and paused workstream: status, last update, how many next, pending, and waiting items it has, and how many resources. Ask for closed ones if you want those too.

## What do next, pending, and waiting mean?

Match: next pending waiting, what is waiting, what does next mean, tracker status

- **Next** — unblocked work you should do before the other items. The first one is the immediate step.
- **Pending** — unblocked work you own that is queued behind that.
- **Waiting** — blocked until someone else sends feedback, a decision, or a reply.

"Follow up with Priya" is next. "Asked Priya and waiting to hear back" is waiting.

## What happens when I start a chat?

Match: start a chat, check-in, /check-in, what happens when I open

On the first message of a day I show each active workstream: what is next, what is pending, and what you are waiting on. I then ask about the oldest stale item, up to three questions. Say skip when you want to stop. `/check-in` runs that review again the same day.

Attached files are listed by name. I do not open them during check-in.

## How do I attach a file, link, or repository?

Match: attach a file, add a resource, /add-resource, add a link, add a repository, drop a file, inbox folder, files in inbox

Send `/add-resource` with the workstream and the file path, URL, or repository URL.

I record it and, for a file, store a copy under that workstream's `resources/` folder. I do not read, fetch, or clone it. Say when you want a link saved as a copy, or a repository kept on disk.

You can also drop a file or a folder into `inbox/`. I ask which workstream each top-level item belongs to, then move it. I do not ask about files inside a dropped folder, and I do not open them unless you later ask me to.

## How do I ask you to read a file?

Match: read a file, analyze a pdf, what does the file say, use the resource

Name the workstream and the file, and say what you want from it. I read the saved note for that file first. If it already answers the question and the file has not changed, I use the note. If a page, sheet, or folder was never opened, the note says so, and I open only that part. A large file is read up to a fixed size. I record what I learned and what I left unread.

## How do I move a note?

Match: move a note, wrong workstream, recategorize

Say which workstream it should be in. I move the note and ask which open items move with it.

## How do I pause, close, or rename?

Match: pause a workstream, close a workstream, rename a workstream, reopen

- **Pause** — tell me to pause it. I stop asking about it and keep the tracker.
- **Close** — tell me to close it. I confirm, write a final note, and clear the tracker.
- **Reopen** — tell me to reopen it.
- **Rename** — give me the new title. I confirm, then rename the folder and the headings.

## What is the .cached folder?

Match: cached folder, .cached, agent memory

That folder is working memory for the agent. It stays aligned with your workstreams so I do not re-read everything on each turn. You do not need to read it or edit it. Your notes, tracker, and files stay under `workstreams/`.

## Can I write in another language?

Match: another language, write in greek, reply in english, which language

Yes. Write in whichever language you want. I store the notes, summaries, and tracker in English. I answer in English unless you explicitly ask for the reply in another language. Asking in Greek, for example, does not by itself switch the reply.
