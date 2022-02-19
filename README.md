# NVDA Speech History

This is an updated version of the Clip Copy add-on for NVDA, initially created by Tyler Spivey in 2012.  Please note that it is compatible with NVDA 2019.3 and 2021.1, but not 22.x alphas.

The original version of the add-on offered two keystrokes:

* F12: Copy the most recent spoken text to the clipboard
* Shift+F12: Toggle an optional beep on new text

This version adds the ability to review up to the 100000 most recent items spoken by NVDA, by default using the hotkeys Shift+F11 and Shift+F12, along with the control modifier for the first and last items respectively.  Pressing F12 will copy the currently selected item from the history, which by default is updated to be the most recent each time NVDA speaks.  In other words, F12 still behaves as it did in the older add-on, unless you've specifically selected an older spoken item to copy.  The beep on new text function has been removed.

The addon in Feburary of 2022 received another revamp, adding a search dialog and history viewer accessed by pressing control f12.
It also added the ability for the cursor not to jump to the latest item whenever NVDA speaks.