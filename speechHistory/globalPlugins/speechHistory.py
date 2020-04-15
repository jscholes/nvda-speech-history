# NVDA Add-on: Speech History
# Copyright (C) 2012 Tyler Spivey
# Copyright (C) 2015-2017 James Scholes
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# See the file LICENSE for more details.

import addonHandler
import api
import globalPluginHandler
from queueHandler import eventQueue, queueFunction
import speech
import speechViewer
import tones
import ui

from globalCommands import SCRCAT_SPEECH

addonHandler.initTranslation()

MAX_HISTORY_LENGTH = 500

oldSpeak = speech.speak
history = []
history_pos = 0


def append_to_history(seq):
	global history, history_pos
	if len(history) == MAX_HISTORY_LENGTH:
		history.pop()
	history.insert(0, seq)
	history_pos = 0


def mySpeak(sequence, *args, **kwargs):
	oldSpeak(sequence, *args, **kwargs)
	text = getSequenceText(sequence)
	if text:
		queueFunction(eventQueue, append_to_history, sequence)


def getSequenceText(sequence):
	return speechViewer.SPEECH_ITEM_SEPARATOR.join([x for x in sequence if isinstance(x, str)])


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super(GlobalPlugin, self).__init__(*args, **kwargs)
		global oldSpeak
		oldSpeak = speech.speak
		speech.speak = mySpeak

	def script_copyLast(self, gesture):
		if api.copyToClip(getSequenceText(history[history_pos])):
			tones.beep(1500, 120)

	# Translators: Documentation string for copy currently selected speech history item script
	script_copyLast.__doc__ = _('Copy the currently selected speech history item to the clipboard, which by default will be the most recently spoken text by NVDA.')
	script_copyLast.category = SCRCAT_SPEECH

	def script_prevString(self, gesture):
		global history_pos
		history_pos += 1
		if history_pos > len(history) - 1:
			tones.beep(200, 100)
			history_pos -= 1

		oldSpeak(history[history_pos])

	# Translators: Documentation string for previous speech history item script
	script_prevString.__doc__ = _('Review the previous item in NVDA\'s speech history.')
	script_prevString.category = SCRCAT_SPEECH

	def script_nextString(self, gesture):
		global history_pos
		history_pos -= 1
		if history_pos < 0:
			tones.beep(200, 100)
			history_pos += 1

		oldSpeak(history[history_pos])

	# Translators: Documentation string for next speech history item script
	script_nextString.__doc__ = _('Review the next item in NVDA\'s speech history.')
	script_nextString.category = SCRCAT_SPEECH

	def terminate(self):
		speech.speak = oldSpeak

	__gestures = {
		"kb:f12":"copyLast",
		"kb:shift+f11":"prevString",
		"kb:shift+f12":"nextString",
	}
