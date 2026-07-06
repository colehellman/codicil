# Regenerate: vhs docs/demo/demo.tape   (run from the repo root)
Output docs/demo/demo.gif

Set Shell bash
Set FontSize 20
Set FontFamily "Menlo"
Set Width 1200
Set Height 640
Set Padding 20
Set TypingSpeed 60ms

# Activate the venv so the demo shows plain `codicil` commands, matching
# real post-install usage. Hidden — not part of the recorded story.
Hide
Type "source .venv/bin/activate"
Enter
Sleep 500ms
Ctrl+L
Show

Type "python docs/demo/query.py 'how does atomic swap reindexing prevent data loss' 1"
Sleep 500ms
Enter
Sleep 5s
