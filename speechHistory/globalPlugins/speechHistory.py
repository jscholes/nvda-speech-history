# NVDA Add-on: Speech History
# Copyright (C) 2012 Tyler Spivey
# Copyright (C) 2015-2021 James Scholes
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# See the file LICENSE for more details.

from collections import deque
import weakref
import wx

import addonHandler
import api
import config
from eventHandler import FocusLossCancellableSpeechCommand
from globalCommands import SCRCAT_SPEECH
import globalPluginHandler
import gui
from gui import guiHelper
from gui import nvdaControls
from gui.dpiScalingHelper import DpiScalingHelperMixin, DpiScalingHelperMixinWithoutInit

from queueHandler import eventQueue, queueFunction
import speech
import speechViewer
import tones
import versionInfo


addonHandler.initTranslation()

BUILD_YEAR = getattr(versionInfo, 'version_year', 2021)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		confspec = {
			'maxHistoryLength': 'integer(default=500)',
			'trimWhitespaceFromStart': 'boolean(default=false)',
			'trimWhitespaceFromEnd': 'boolean(default=false)',
		}
		config.conf.spec['speechHistory'] = confspec
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SpeechHistorySettingsPanel)

		self._history = deque(maxlen=config.conf['speechHistory']['maxHistoryLength'])
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

	def mySpeak(self, sequence, *args, **kwargs):
		self.oldSpeak(sequence, *args, **kwargs)
		text = self.getSequenceText(sequence)
		if text.strip():
			queueFunction(eventQueue, self.append_to_history, sequence)

	def getSequenceText(self, sequence):
		return speechViewer.SPEECH_ITEM_SEPARATOR.join([x for x in sequence if isinstance(x, str)])

	def script_showHistorial(self, gesture):
		gui.mainFrame.prePopup()
		HistoryDialog(gui.mainFrame, [self.getSequenceText(k) for k in self._history]).Show()
		gui.mainFrame.postPopup()


	__gestures = {
		"kb:f12":"copyLast",
		"kb:shift+f11":"prevString",
		"kb:shift+f12":"nextString",
		"kb:nvda+control+f12":"showHistorial",
	}


class SpeechHistorySettingsPanel(gui.SettingsPanel):
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

	def onSave(self):
		config.conf['speechHistory']['maxHistoryLength'] = self.maxHistoryLengthEdit.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromStart'] = self.trimWhitespaceFromStartCB.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromEnd'] = self.trimWhitespaceFromEndCB.GetValue()



class HistoryDialog(
		DpiScalingHelperMixinWithoutInit,
		gui.contextHelp.ContextHelpMixin,
		wx.Dialog  # wxPython does not seem to call base class initializer, put last in MRO
):
	@classmethod
	def _instance(cls):
		""" type: () -> HistoryDialog
		return None until this is replaced with a weakref.ref object. Then the instance is retrieved
		with by treating that object as a callable.
		"""
		return None

	helpId = "SpeechHistoryElementsList"

	def __new__(cls, *args, **kwargs):
		instance = HistoryDialog._instance()
		if instance is None:
			return super(HistoryDialog, cls).__new__(cls, *args, **kwargs)
		return instance

	def __init__(self, parent, history):
		if HistoryDialog._instance() is not None:
			return
		HistoryDialog._instance = weakref.ref(self)
		# Translators: The title of the history elements Dialog
		title = _("Speech histori elements")
		super().__init__(
			parent,
			title=title,
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
		)
		# the original speech history messages list.
		self.history = history
		# the results of a search, initially equals to history
		self.searchHistory = history
		# indexes of search, to save the selected item in a specific search.
		self.searches = {"": 0}
		# the current search, initially "".
		self.curSearch = ""

		szMain = guiHelper.BoxSizerHelper(self, sizer=wx.BoxSizer(wx.VERTICAL))
		szBottom = guiHelper.BoxSizerHelper(self, sizer=wx.BoxSizer(wx.HORIZONTAL))

		# Translators: the label for the search text field in the speech history add-on.
		self.searchTextFiel = szMain.addLabeledControl(_("&Search"),
			wx.TextCtrl,
			style =wx.TE_PROCESS_ENTER
		)
		self.searchTextFiel.Bind(wx.EVT_TEXT_ENTER, self.onSearch)

		# Translators: the label for the history elements list in the speech history add-on.
		entriesLabel = _("History list")
		self.historyList = nvdaControls.AutoWidthColumnListCtrl(
			parent=self,
			autoSizeColumn=1,
			style=wx.LC_REPORT|wx.LC_SINGLE_SEL|wx.LC_NO_HEADER
			)
		
		szMain.addItem(
			self.historyList,
			flag=wx.EXPAND,
			proportion=1,
		)
		# This list consists of only one column.
		# The provided column header is just a placeholder, as it is hidden due to the wx.LC_NO_HEADER style flag.
		self.historyList.InsertColumn(0, entriesLabel)
		self.historyList.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.onListItemSelected)

		# a multiline text field containing the text from the current selected element.
		self.currentTextElement = szMain.addItem(
			wx.TextCtrl(self, style =wx.TE_MULTILINE|wx.TE_READONLY),
			flag=wx.EXPAND,
			proportion=1
		)

		szMain.addItem(
			wx.StaticLine(self),
			border=guiHelper.BORDER_FOR_DIALOGS,
			flag=wx.ALL | wx.EXPAND
		)

		# Translators: the label for the copy button in the speech history add-on.
		self.copyButton = szBottom.addItem(wx.Button(self, label=_("&Copy item")))
		self.copyButton.Bind(wx.EVT_BUTTON, self.onCopy)

		# Translators: the label for the copy all button in the speech history add-on. This is based on the current search.
		self.copyAllButton = szBottom.addItem(wx.Button(self, label=_("Copy &all")))
		self.copyAllButton.Bind(wx.EVT_BUTTON, self.onCopyAll)

		# Translators: The label of a button to close the speech history dialog.
		closeButton = wx.Button(self, label=_("C&lose"), id=wx.ID_CLOSE)
		closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.Close())
		szBottom.addItem(closeButton)
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.EscapeId = wx.ID_CLOSE

		szMain.addItem(
			szBottom.sizer,
			border=guiHelper.BORDER_FOR_DIALOGS,
			flag=wx.ALL | wx.EXPAND,
			proportion=1,
		)
		szMain = szMain.sizer
		szMain.Fit(self)
		self.SetSizer(szMain)
		self.doSearch()

		self.SetMinSize(szMain.GetMinSize())
		# Historical initial size, result of L{self.historyList} being (550, 350)
		# Setting an initial size on L{self.historyList} by passing a L{size} argument when
		# creating the control would also set its minimum size and thus block the dialog from being shrunk.
		self.SetSize(self.scaleSize((763, 509)))
		self.CentreOnScreen()
		self.historyList.SetFocus()

	def onListItemSelected(self, evt):
		index=evt.GetIndex()
		self.currentTextElement.SetValue(self.history[index])

	def onSearch(self, evt):
		t = self.searchTextFiel.GetValue().lower()
		self.searches[self.curSearch] = self.historyList.GetFirstSelected()
		self.curSearch = t
		self.doSearch(t)

	def doSearch(self, text=""):
		if not text:
			self.searchHistory = self.history
		else:
			self.searchHistory = [k for k in self.searchHistory if text in k.lower()]
		self.historyList.DeleteAllItems()
		for k in self.searchHistory: self.historyList.Append((k[0:100],))
		if len(self.searchHistory) >0:
			if text not in self.searches:
				self.searches[text] = 0
			index = self.searches[text]
			self.historyList.Select(index, on=1)
			self.historyList.SetItemState(index,wx.LIST_STATE_FOCUSED,wx.LIST_STATE_FOCUSED)

	def onClose(self,evt):
		self.DestroyChildren()
		self.Destroy()

	def onCopy(self,evt):
		t = self.currentTextElement.GetValue()
		if t:
			api.copyToClip(t)

	def onCopyAll(self, evt):
		t = ""
		for k in self.searchHistory: t+= k+"\n"
		if t:
			api.copyToClip(t)
