# Conversation selection and folders

Click a chat to read it. Ctrl-click (or Command-click) toggles individual selections without opening them. Shift-click selects the range between the last clicked chat and the clicked row, in the current displayed order. Ctrl+Shift adds a range. **Select chats** enables click-to-toggle selection without a keyboard; **Done selecting** returns to ordinary opening.

The sidebar uses a single compact row: **Select chats** and **Tools** (which shows the current selected count). Tools opens a draggable, resizable panel containing All visible, Invert visible, Clear, Select subagents, Hide subagents, Back up selected and Queue deletion. Drag its heading to reposition it; resize from its lower corner. Click outside or press Escape to close the panel without clearing the selected chats. With the panel closed, Escape clears selection outside inputs and other dialogs.

All visible and Invert visible operate on the currently displayed rows, including the current search, type, filters, collapsed groups and Show more limits. Invert replaces the selection with the visible complement. The selected count explicitly reports selected chats that are hidden. Changing filters removes selections outside the matching scope. Selection resets on refresh; no deletion starts automatically.

Queue deletion opens the existing source-specific review dialog. Native Codex, ChatGPT-linked, temporary and local-only chats retain their existing deletion choices. Mixed source types must be reviewed separately. Queueing and running remain separate actions.

Codex subagents are hidden by default. Uncheck Hide subagents to show them; this preference survives refresh and restart. Select subagents selects every matching Codex subagent, including those hidden by this toggle or collapsed sections. It respects the current search, filters and conversation type. Only producer subagent metadata qualifies: rollout-style names and ordinary forks do not.

The open conversation offers Home folder when a workspace was recorded and Source folder for its saved transcript directory. Linked local directories render as folder cards and open in Explorer on Windows. Folder paths come from recorded metadata or exact links in the saved conversation. Missing folders produce feedback; the viewer does not create them. These actions do not change workspace files or conversation data.
