# NVDA Add-on: Speech History
# Copyright (C) 2012 Tyler Spivey
# Copyright (C) 2015-2021 James Scholes
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# See the file LICENSE for more details.

from collections import deque

import wx

import addonHandler
import api
import config
from eventHandler import FocusLossCancellableSpeechCommand
from globalCommands import SCRCAT_SPEECH
import globalPluginHandler
import gui
from gui import nvdaControls
from queueHandler import eventQueue, queueFunction
import speech
import speechViewer
import tones
import versionInfo
from logHandler import log
from enum import Enum


try:
	addonHandler.initTranslation()
except addonHandler.AddonError:
	log.warning('Unable to init translations. This may be because the addon is running from NVDA scratchpad.')


BUILD_YEAR = getattr(versionInfo, 'version_year', 2021)

class CursorBehaviors(Enum):
	latest= _('move focus to the new item')
	context= _('sync focus with the current context')
	index= _('keep focus on the current index')


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		confspec = {
			'maxHistoryLength': 'integer(default=500)',
			'trimWhitespaceFromStart': 'boolean(default=false)',
			'trimWhitespaceFromEnd': 'boolean(default=false)',
			'cursorBehavior': 'string(default=latest)',
		}
		config.conf.spec['speechHistory'] = confspec
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SpeechHistorySettingsPanel)

		self._history = deque(maxlen=config.conf['speechHistory']['maxHistoryLength'])
		self.history_pos = 0
		self._recorded = []
		self._recording = False
		self._patch()

	def _patch(self):
		if BUILD_YEAR >= 2021:
			self.oldSpeak = speech.speech.speak
			speech.speech.speak = self.mySpeak
		else:
			self.oldSpeak = speech.speak
			speech.speak = self.mySpeak

	def script_copyLast(self, gesture):
		text = self.getSequenceText(self._history[self.history_pos])
		if config.conf['speechHistory']['trimWhitespaceFromStart']:
			text = text.lstrip()
		if config.conf['speechHistory']['trimWhitespaceFromEnd']:
			text = text.rstrip()
		if api.copyToClip(text):
			tones.beep(1500, 120)

	# Translators: Documentation string for copy currently selected speech history item script
	script_copyLast.__doc__ = _('Copy the currently selected speech history item to the clipboard, which by default will be the most recently spoken text by NVDA.')
	script_copyLast.category = SCRCAT_SPEECH

	def script_prevString(self, gesture):
		self.history_pos += 1
		if self.history_pos > len(self._history) - 1:
			tones.beep(200, 100)
			self.history_pos -= 1
		self.oldSpeak(self._history[self.history_pos])
	# Translators: Documentation string for previous speech history item script
	script_prevString.__doc__ = _('Review the previous item in NVDA\'s speech history.')
	script_prevString.category = SCRCAT_SPEECH

	def script_nextString(self, gesture):
		self.history_pos -= 1
		if self.history_pos < 0:
			tones.beep(200, 100)
			self.history_pos += 1

		self.oldSpeak(self._history[self.history_pos])
	# Translators: Documentation string for next speech history item script
	script_nextString.__doc__ = _('Review the next item in NVDA\'s speech history.')
	script_nextString.category = SCRCAT_SPEECH

	def script_firstString(self, gesture):
		self.history_pos = len(self._history)-1
		tones.beep(350, 150)
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for first speech history item script
	script_firstString.__doc__ =_('Review the first item in NVDA\'s speech history.')
	script_firstString.category = SCRCAT_SPEECH

	def script_lastString(self, gesture):
		self.history_pos = 0
		tones.beep(350, 150)
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for last speech history item script
	script_lastString.__doc__ =_('Review the last item in NVDA\'s speech history.')
	script_lastString.category = SCRCAT_SPEECH

	def script_moveCursor(self, gesture):
		behaviors= [o.name for o in CursorBehaviors]
		index= behaviors.index(config.conf['speechHistory']['cursorBehavior'])+1
		if index== len(behaviors):
			index=0
		config.conf['speechHistory']['cursorBehavior']= behaviors[index]
		# Translators: cursor behavior changed
		self.oldSpeak([CursorBehaviors[behaviors[index]].value])

	# Translators: Documentation string for cursor behavior script
	script_moveCursor.__doc__ = _('Change where the speech history cursor should move when NVDA speaks.')
	script_moveCursor.category = SCRCAT_SPEECH

	def script_startRecording(self, gesture):
		if self._recording:
			# Translators: Message spoken when speech recording is already active
			self.oldSpeak([_('Already recording speech')])
			return

		# Translators: Message spoken when speech recording is started
		self.oldSpeak([_('Started recording speech')])
		self._recording = True
	# Translators: Documentation string for start recording script
	script_startRecording.__doc__ = _('Start recording NVDA\'s speech output, for copying multiple announcements to the clipboard.')
	script_startRecording.category = SCRCAT_SPEECH

	def script_stopRecording(self, gesture):
		if not self._recording:
			# Translators: Message spoken when speech recording is not already active
			self.oldSpeak([_('Not currently recording speech')])
			return

		self._recording = False
		# Translators: Message spoken when speech recording is stopped
		self.oldSpeak([_('Recorded speech copied to clipboard')])
		api.copyToClip('\n'.join(self._recorded))
		self._recorded.clear()
	# Translators: Documentation string for stop recording script
	script_stopRecording.__doc__ = _('Stop recording NVDA\'s speech output, and copy the recorded announcements to the clipboard.')
	script_stopRecording.category = SCRCAT_SPEECH

	def terminate(self, *args, **kwargs):
		super().terminate(*args, **kwargs)
		if BUILD_YEAR >= 2021:
			speech.speech.speak = self.oldSpeak
		else:
			speech.speak = self.oldSpeak
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SpeechHistorySettingsPanel)

	def append_to_history(self, seq):
		seq = [command for command in seq if not isinstance(command, FocusLossCancellableSpeechCommand)]
		self._history.appendleft(seq)
		if config.conf['speechHistory']['cursorBehavior']== 'latest':
			self.history_pos = 0
		elif config.conf['speechHistory']['cursorBehavior']== 'context':
			if len(self._history)>1 and self.history_pos< config.conf['speechHistory']['maxHistoryLength']-1:
				self.history_pos += 1
				if self.history_pos== config.conf['speechHistory']['maxHistoryLength']-1:
					tones.beep(750, 200)
		if self._recording:
			self._recorded.append(self.getSequenceText(seq))

	def mySpeak(self, sequence, *args, **kwargs):
		self.oldSpeak(sequence, *args, **kwargs)
		text = self.getSequenceText(sequence)
		if text.strip():
			queueFunction(eventQueue, self.append_to_history, sequence)

	def getSequenceText(self, sequence):
		return speechViewer.SPEECH_ITEM_SEPARATOR.join([x for x in sequence if isinstance(x, str)])

	__gestures = {
		"kb:f12":"copyLast",
		"kb:shift+f11":"prevString",
		"kb:shift+f12":"nextString",
		"kb:control+shift+f11":"firstString",
		"kb:control+shift+f12":"lastString",
		"kb:control+f11":"moveCursor",
		"kb:NVDA+shift+f11":"startRecording",
		"kb:NVDA+shift+f12":"stopRecording",
	}


class SpeechHistorySettingsPanel(gui.settingsDialogs.SettingsPanel):
	# Translators: the label/title for the Speech History settings panel.
	title = _('Speech History')

	def makeSettings(self, settingsSizer):
		helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: the label for the preference to choose the maximum number of stored history entries
		maxHistoryLengthLabelText = _('&Maximum number of history entries (requires NVDA restart to take effect)')
		self.maxHistoryLengthEdit = helper.addLabeledControl(maxHistoryLengthLabelText, nvdaControls.SelectOnFocusSpinCtrl, min=1, max=5000, initial=config.conf['speechHistory']['maxHistoryLength'])
		# Translators: the label for the preference to trim whitespace from the start of text
		self.trimWhitespaceFromStartCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &start when copying text')))
		self.trimWhitespaceFromStartCB.SetValue(config.conf['speechHistory']['trimWhitespaceFromStart'])
		# Translators: the label for the preference to trim whitespace from the end of text
		self.trimWhitespaceFromEndCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &end when copying text')))
		self.trimWhitespaceFromEndCB.SetValue(config.conf['speechHistory']['trimWhitespaceFromEnd'])
		# Translators: the label for the preference to set the cursor behavior
		moveCursorLabelText= _('When NVDA Speaks, The &Cursor Should')
		behaviors= [o.name for o in CursorBehaviors]
		self.moveCursorChoice = helper.addLabeledControl(moveCursorLabelText, wx.Choice, choices = [o.value for o in CursorBehaviors])
		self.moveCursorChoice.SetSelection(behaviors.index(config.conf['speechHistory']['cursorBehavior']))

	def onSave(self):
		config.conf['speechHistory']['maxHistoryLength'] = self.maxHistoryLengthEdit.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromStart'] = self.trimWhitespaceFromStartCB.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromEnd'] = self.trimWhitespaceFromEndCB.GetValue()
		behaviors= [o.name for o in CursorBehaviors]
		config.conf['speechHistory']['cursorBehavior'] = behaviors[self.moveCursorChoice.GetCurrentSelection()]
