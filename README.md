# NVDA Speech History
This is an updated version of the Clip Copy add-on for NVDA, initially created by Tyler Spivey in 2012.  The add-on is compatible with NVDA versions from 2020.4 to 2024.1.

The original version of the add-on offered two keystrokes:
* F12: Copy the most recent spoken text to the clipboard
* Shift+F12: Toggle an optional beep on new text

In this version:
* You can review the 500 most recent items spoken by NVDA, by default using the hotkeys Shift+F11 and Shift+F12.
* Pressing F12 will copy the currently selected item from the history, which is updated to be the most recent each time NVDA speaks.  In other words, F12 still behaves as it did in the older add-on, unless you've specifically selected an older spoken item to copy.
* You can capture multiple speech history items in realtime, which is useful for e.g. bug reports without copying from the Speech Viewer.  Press NVDA+Shift+F11 to start recording, use NVDA as normal, and then press NVDA+Shift+F12 to stop recording.  All recorded speech will be copied to the clipboard, with items separated by a line break (`\n`).
* You can open a full speech history dialog with NVDA+Alt+F12. The dialog supports search, multi-selection, copy selected items, copy all filtered items, refresh, and clear history.
* The beep on new text function has been removed.
