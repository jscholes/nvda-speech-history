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
import globalPluginHandler
import gui
import speech
import speechViewer
import tones
import versionInfo
from queueHandler import queueFunction, eventQueue
from eventHandler import FocusLossCancellableSpeechCommand
from gui import nvdaControls
from globalCommands import SCRCAT_SPEECH


addonHandler.initTranslation()


CONFIG_SECTION = 'speechHistory'

POST_COPY_NOTHING = 'nothing'
POST_COPY_BEEP = 'beep'
POST_COPY_SPEAK = 'speak'
POST_COPY_BOTH = 'speakAndBeep'

DEFAULT_POST_COPY_ACTION = POST_COPY_BEEP

BUILD_YEAR = getattr(versionInfo, 'version_year', 2021)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		confspec = {
			'maxHistoryLength': 'integer(default=500)',
			'postCopyAction': f'string(default={DEFAULT_POST_COPY_ACTION})',
			'trimWhitespaceFromStart': 'boolean(default=false)',
			'trimWhitespaceFromEnd': 'boolean(default=false)',
		}
		config.conf.spec[CONFIG_SECTION] = confspec
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SpeechHistorySettingsPanel)

		self._history = deque(maxlen=config.conf[CONFIG_SECTION]['maxHistoryLength'])
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
		if config.conf[CONFIG_SECTION]['trimWhitespaceFromStart']:
			text = text.lstrip()
		if config.conf[CONFIG_SECTION]['trimWhitespaceFromEnd']:
			text = text.rstrip()

		postCopyAction = config.conf[CONFIG_SECTION]['postCopyAction']
		if api.copyToClip(text):
			if postCopyAction in (POST_COPY_BEEP, POST_COPY_BOTH):
				tones.beep(1500, 120)
			if postCopyAction in (POST_COPY_SPEAK, POST_COPY_BOTH):
				# Translators: A short confirmation message spoken after copying a speech history item.
				self.oldSpeak([_('Copied')])

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
		self.history_pos = 0
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
		self.maxHistoryLengthEdit = helper.addLabeledControl(maxHistoryLengthLabelText, nvdaControls.SelectOnFocusSpinCtrl, min=1, max=5000, initial=config.conf[CONFIG_SECTION]['maxHistoryLength'])

		# Translators: The label for the preference of what to do after copying a speech history item to the clipboard. The options are "Do nothing", "Beep", "Speak", or "Beep and speak".
		postCopyActionComboText = _('&After copying speech:')
		postCopyActionChoices = [
			# Translators: A SpeechHistory option to have NVDA do nothing (no beep or speech) after copying a history item.
			_('Do nothing'),
			# Translators: A SpeechHistory option to have NVDA beep after copying a history item.
			_('Beep'),
			# Translators: A SpeechHistory option to have NVDA speak confirmation after copying a history item.
			_('Speak'),
			# Translators: A SpeechHistory option to have NVDA both beep and speak as confirmation after copying a history item.
			_('Both beep and speak'),
		]
		self.postCopyActionValues = (POST_COPY_NOTHING, POST_COPY_BEEP, POST_COPY_SPEAK, POST_COPY_BOTH)
		self.postCopyActionCombo = helper.addLabeledControl(postCopyActionComboText, wx.Choice, choices=postCopyActionChoices)
		self.postCopyActionCombo.SetSelection(self.postCopyActionValues.index(config.conf[CONFIG_SECTION]['postCopyAction']))
		self.postCopyActionCombo.defaultValue = self.postCopyActionValues.index(DEFAULT_POST_COPY_ACTION)

		# Translators: the label for the preference to trim whitespace from the start of text
		self.trimWhitespaceFromStartCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &start when copying text')))
		self.trimWhitespaceFromStartCB.SetValue(config.conf[CONFIG_SECTION]['trimWhitespaceFromStart'])

		# Translators: the label for the preference to trim whitespace from the end of text
		self.trimWhitespaceFromEndCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &end when copying text')))
		self.trimWhitespaceFromEndCB.SetValue(config.conf[CONFIG_SECTION]['trimWhitespaceFromEnd'])

	def onSave(self):
		config.conf[CONFIG_SECTION]['maxHistoryLength'] = self.maxHistoryLengthEdit.GetValue()
		config.conf[CONFIG_SECTION]['postCopyAction'] = self.postCopyActionValues[self.postCopyActionCombo.GetSelection()]
		config.conf[CONFIG_SECTION]['trimWhitespaceFromStart'] = self.trimWhitespaceFromStartCB.GetValue()
		config.conf[CONFIG_SECTION]['trimWhitespaceFromEnd'] = self.trimWhitespaceFromEndCB.GetValue()
