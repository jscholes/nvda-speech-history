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
import json
import globalVars
import os
import time

try:
	addonHandler.initTranslation()
except addonHandler.AddonError:
	log.warning('Unable to init translations. This may be because the addon is running from NVDA scratchpad.')

BUILD_YEAR = getattr(versionInfo, 'version_year', 2021)
folder= globalVars.appArgs.configPath
maxItems=0
totalItems=0

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		global maxItems
		confspec = {
			'maxHistoryLength': 'integer(default=10000)',
			'trimWhitespaceFromStart': 'boolean(default=false)',
			'trimWhitespaceFromEnd': 'boolean(default=false)',
			'moveFocus': 'string(default=move focus to the new item)',
			'autoExport': 'boolean(default=false)',
			#search options
			'searchBy': 'string(default=text)',
			'whereInString': 'option("anywhere", "full", "beginning", "middle", "end", "nowhere" default=anywhere)',
			'caseSensitive': 'boolean(default=false)',
			'queryResultsAsYouType': 'boolean(default=false)',
			'sequenceIndexes': 'string(default=0 )',
			# Translators: for some strange reason, we need to put a space after the 0, but later on it won't complain. Because at first it thinks it is an integer.
			'inverseIndexes': 'boolean(default=false)',
			# Translators: this variable is not seen by the user directly; it is toggled via an exclamation in sequenceIndexes.
			'resetFields': 'boolean(default=true)',
		}
		config.conf.spec['speechHistory'] = confspec
		if config.conf['speechHistory']['sequenceIndexes']== '0 ':
			config.conf['speechHistory']['sequenceIndexes']= '0'
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SpeechHistorySettingsPanel)

		self.history_pos = 0
		maxItems= config.conf['speechHistory']['maxHistoryLength']
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
		if len(self._history)==0:
			return
		copyText(self.getSequenceText(self._history[self.history_pos]))

	# Translators: Documentation string for copy currently selected speech history item script
	script_copyLast.__doc__ = _('Copy the currently selected speech history item to the clipboard.')
	script_copyLast.category = SCRCAT_SPEECH

	def script_prevString(self, gesture):
		if len(self._history)==0:
			return
		self.history_pos += 1
		if self.history_pos > len(self._history) - 1:
			tones.beep(200, 100)
			self.history_pos -= 1
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for previous speech history item script
	script_prevString.__doc__ = _('Review the previous item in NVDA\'s speech history.')
	script_prevString.category = SCRCAT_SPEECH

	def script_nextString(self, gesture):
		if len(self._history)==0:
			return
		self.history_pos -= 1
		if self.history_pos < 0:
			tones.beep(200, 100)
			self.history_pos += 1
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for next speech history item script
	script_nextString.__doc__ = _('Review the next item in NVDA\'s speech history.')
	script_nextString.category = SCRCAT_SPEECH

	def script_firstString(self, gesture):
		if len(self._history)==0:
			return
		self.history_pos = len(self._history)-1
		tones.beep(350, 150)
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for first speech history item script
	script_firstString.__doc__ = _('Review the first item in NVDA\'s speech history.')
	script_firstString.category = SCRCAT_SPEECH

	def script_lastString(self, gesture):
		if len(self._history)==0:
			return
		self.history_pos = 0
		tones.beep(350, 150)
		self.oldSpeak(self._history[self.history_pos])

	# Translators: Documentation string for last speech history item script
	script_lastString.__doc__ = _('Review the last item in NVDA\'s speech history.')
	script_lastString.category = SCRCAT_SPEECH

	def script_moveFocus(self, gesture):
		options= ['move focus to the new item', 'sync focus with the current item', 'keep focus on the current index']
		o= options.index(config.conf['speechHistory']['moveFocus'])
		o+=1
		if o== len(options):
			o=0
		config.conf['speechHistory']['moveFocus']= options[o]
		self.oldSpeak([config.conf['speechHistory']['moveFocus']])

	# Translators: Documentation string for move focus script
	script_moveFocus.__doc__ = _('Change where the speech history cursor should move when NVDA speaks.')
	script_moveFocus.category = SCRCAT_SPEECH

	def script_searchHistory(self, gesture):
		self.launchSearch()

	# Translators: Documentation string for speech history search script
	script_searchHistory.__doc__ = _('Open the speech history search dialog and history viewer.')
	script_searchHistory.category = SCRCAT_SPEECH

	def launchSearch(self):
		self.oldSpeak(['Search launched.'])
		sd= SearchDialog(history= self._history)

	def resetHistory(self):
		global totalItems
		totalItems=0
		self.history_pos=0
		self._history.clear()

	def terminate(self, *args, **kwargs):
		super().terminate(*args, **kwargs)
		if config.conf['speechHistory']['autoExport'] and cycleRemainder()>0:
			exportHistory(self._history, end= cycleRemainder())
		self.resetHistory()
		config.conf['speechHistory']['maxHistoryLength']= maxItems
		if BUILD_YEAR >= 2021:
			speech.speech.speak = self.oldSpeak
		else:
			speech.speak = self.oldSpeak
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SpeechHistorySettingsPanel)

	def append_to_history(self, seq):
		global totalItems
		seq = [command for command in seq if not isinstance(command, FocusLossCancellableSpeechCommand)]
		if wx.GetActiveWindow() and wx.GetActiveWindow().Label.find('Speech History')>-1:
			return
		self._history.appendleft(seq)
		totalItems+=1
		if config.conf['speechHistory']['autoExport'] and cycleRemainder()==0:
			exportHistory(self._history)
		if config.conf['speechHistory']['moveFocus']== 'move focus to the new item':
			self.history_pos = 0
		elif config.conf['speechHistory']['moveFocus']== 'sync focus with the current item':
			if totalItems>1 and self.history_pos< config.conf['speechHistory']['maxHistoryLength']-1:
				self.history_pos += 1
				if self.history_pos== config.conf['speechHistory']['maxHistoryLength']-1:
					tones.beep(750, 200)

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
		"kb:control+f11":"moveFocus",
		"kb:control+f12":"searchHistory",
	}


class SpeechHistorySettingsPanel(gui.SettingsPanel):
	# Translators: the label/title for the Speech History settings panel.
	title = _('Speech History')

	def makeSettings(self, settingsSizer):
		helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: the label for the preference to choose the maximum number of stored history entries
		maxHistoryLengthLabelText = _('&Maximum number of history entries (requires NVDA restart to take effect)')
		self.maxHistoryLengthEdit = helper.addLabeledControl(maxHistoryLengthLabelText, nvdaControls.SelectOnFocusSpinCtrl, min=1, max=100000, initial=maxItems)
		# Translators: the label for the preference to trim whitespace from the start of text
		self.trimWhitespaceFromStartCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &start when copying text')))
		self.trimWhitespaceFromStartCB.SetValue(config.conf['speechHistory']['trimWhitespaceFromStart'])
		# Translators: the label for the preference to trim whitespace from the end of text
		self.trimWhitespaceFromEndCB = helper.addItem(wx.CheckBox(self, label=_('Trim whitespace from &end when copying text')))
		self.trimWhitespaceFromEndCB.SetValue(config.conf['speechHistory']['trimWhitespaceFromEnd'])
		# Translators: the preference to choose where focus is moved when NVDA speaks
		self.moveFocusLabel= wx.StaticText(self, label= 'When NVDA Speaks, The &Cursor Should:')
		self.moveFocus= wx.Choice(self, choices= ['move focus to the new item', 'sync focus with the current item', 'keep focus on the current index'])
		self.moveFocus.Select(self.moveFocus.FindString(config.conf['speechHistory']['moveFocus']))
		# Translators: the label for the preference to toggle if history is automatically exported to a file
		self.autoExport= helper.addItem(wx.CheckBox(self, label=_('Automatically Export Current History Into A Json &File When The Max Length Is Reached And When NVDA Restarts')))
		self.autoExport.SetValue(config.conf['speechHistory']['autoExport'])
		# Translators: the reset button
#		self.reset= wx.Button(self, label= 'Reset All Settings')
#		self.reset.Bind(wx.EVT_BUTTON, self.onReset)
		# Translators: I don't know which class has the reset method

#	def onReset(self, event: wx._core.PyEvent):
#				config.conf.spec['speechHistory'].reset()
		 #Translators: not sure how to remake the window to display the default settings, maybe window.refresh?

	def onSave(self):
		global maxItems
		maxItems= self.maxHistoryLengthEdit.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromStart'] = self.trimWhitespaceFromStartCB.GetValue()
		config.conf['speechHistory']['trimWhitespaceFromEnd'] = self.trimWhitespaceFromEndCB.GetValue()
		config.conf['speechHistory']['moveFocus'] = self.moveFocus.GetString(self.moveFocus.GetCurrentSelection())
		config.conf['speechHistory']['autoExport'] = self.autoExport.GetValue()

# Translators: functions for list boxes

class LB():
	def validIndex(window, l, needsIndex=True, alerts= ['empty', 'unselected']):
		if l.GetCount()==0:
			if 'empty' in alerts:
				gui.messageBox('This list has no items.', caption= 'Invalid Operation', parent= window)
			return False
		if needsIndex and l.GetSelection()==-1:
			if 'unselected' in alerts:
				gui.messageBox('No item is selected.', caption= 'Invalid Operation', parent= window)
			return False
		return True

	def readIndex(window, l, filter=None):
		# Translators: the filter variable is a list that points to history indexes since the listbox does not account for them.
		if not LB.validIndex(window, l):
			return
		index= l.GetSelection()
		gui.messageBox(str((index if filter is None else filter[index])+1), caption= 'Index Number', parent=window)

	def copyIndex(window, l):
		if not LB.validIndex(window, l):
			return
		copyText(l.GetString(l.GetSelection()))

class SearchDialog(wx.Frame):
	def __init__(self, *, history):
		self._originalHistory= history
		self._history= self.updateHistory()
		self.selection= {'list': None, 'index': 0, 'tempSelection': [], 'data': []}
		self.data= {'query': '', 'results': [], 'focusedResult': 0}
		#query: the user's search term. Can be text or an index number.
		#results: a list containing dictionaries for the queried results; index: the index in the history, sequence: the history item, text: the concatinated sequence after filtered
		#focused result: the selected index in the queried results
		super().__init__(parent=None, title='Speech History Search')
		self.makeSettings()
		self.Show()

	def updateHistory(self):
		history= self._originalHistory.copy()
		history.reverse()
		# Translators: sort from oldest to newest
		return history

	def makeSettings(self, query='', results=[]):
		panel = wx.Panel(self)
		# Translators: the search label and edit box
		self.searchLabel= wx.StaticText(panel, label= '&Search '+config.conf['speechHistory']['searchBy'])
		self.search= wx.TextCtrl(panel, value= query, style= wx.TE_MULTILINE)
		# Translators: bind a text update event handler if the queryResultsAsYouType option is enabled. Otherwise, add a query results button and bind it. Both binders point to the same function.
		if config.conf['speechHistory']['queryResultsAsYouType']:
			self.search.Bind(wx.EVT_TEXT, self.onQuery)
		else:
			self.query= wx.Button(panel, label= '&Query Results')
			self.query.Bind(wx.EVT_BUTTON, self.onQuery)
		# Translators: the options button.
		self.settings= wx.Button(panel, label= '&Options')
		self.settings.Bind(wx.EVT_BUTTON, self.onSettings)
		# Translators: the results label and list box
		self.resultsLabel= wx.StaticText(panel, label= f'{len(results)} &Result'+('s' if len(results)!= 1 else '')+' Available')
		self.results= wx.ListBox(panel, choices=results)
		# Translators: the readIndex button
		self.readIndex= wx.Button(panel, label= 'Read history &Index Number')
		self.readIndex.Bind(wx.EVT_BUTTON, self.onIndex)
		# Translators: the copyItem button
		self.copyItem= wx.Button(panel, label= '&Copy Item To Clipboard')
		self.copyItem.Bind(wx.EVT_BUTTON, self.onCopy)
		# Translators: the open history viewer button.
		self.view= wx.Button(panel, label= 'Open &History Viewer')
		self.view.Bind(wx.EVT_BUTTON, self.onView)
		# Translators: the update history button.
		self.update= wx.Button(panel, label= '&Update History')
		self.update.Bind(wx.EVT_BUTTON, self.onUpdate)
		# Translators: the exit button.
		self.exit= wx.Button(panel, label= '&Exit')
		self.exit.Bind(wx.EVT_BUTTON, self.onExit)
		# Translators: enable keyboard events, escape will bind to onExit function.
		panel.Bind(wx.EVT_CHAR_HOOK, self.onKey)
		panel.SetFocus()

	def onQuery(self, event=None):
		# Translators: text updated event handler and query results button binder
		self.data['query']= self.search.GetValue()
		if len(self._history)==0:
			gui.messageBox(_('There are no items in the history.'), caption= _('Empty History'), parent= self)
			return
		if not self.data['query']:
			self.clearResults()
			return
		text= self.data['query']
		if config.conf['speechHistory']['searchBy']== 'index':
			if not text.isdigit():
				gui.messageBox(_('Input must be a number.'), caption= _('Invalid Query'), parent= self)
				if config.conf['speechHistory']['queryResultsAsYouType']:
					self.data['query']= self.data['query'][:-1]
					self.search.SetValue(self.data['query'])
				return
			text= int(text)-1
			if text<0 or text>= len(self._history):
				gui.messageBox(_(f'Input must be between 1 and {len(self._history)}.'), caption= _('Invalid Query'), parent= self)
				if config.conf['speechHistory']['queryResultsAsYouType']:
					self.data['query']= self.data['query'][:-1]
					self.search.SetValue(self.data['query'])
				return
		self.clearResults()
		self.results.Set(self.queryResults(self._history if config.conf['speechHistory']['searchBy']== 'text' else [self._history[text]], text))
		# Translators: send all history items if we are searching by text, otherwise we just send the one history item with the quieried index.
		self.resultsLabel.SetLabel(f'{self.results.GetCount()} &Result'+('s' if self.results.GetCount()!= 1 else '')+' Available')

	def onSettings(self, event: wx._core.PyEvent):
		options= SearchOptions(self)
		if options.ShowModal()== wx.ID_OK:
			self.makeSettings(self.data['query'], [self.results.GetString(r) for r in range(self.results.GetCount())] if self.results.GetCount()>0 else [])
		self.onQuery()
		self.settings.SetFocus()

	def onIndex(self, event: wx._core.PyEvent):
		LB.readIndex(self, self.results, [r['index'] for r in self.data['results']])

	def onCopy(self, event: wx._core.PyEvent):
		LB.copyIndex(self, self.results)

	def onView(self, event: wx._core.PyEvent):
		# Translators: open history viewer binder
		if len(self._history)==0:
			gui.messageBox(_('There are no items in the history.'), caption= _('Empty History'), parent= self)
			return
		if LB.validIndex(self, self.results, alerts=[]):
			self.data['focusedResult']= self.data['results'][self.results.GetSelection()]['index']
			# Translators: if there is a selected index, the focused result is changed from 0. Logic: newIndex= dataResults[index from listBox][index in history]
		viewer= HistoryViewer(self, history= self._history, selection= self.selection, index= self.data['focusedResult'])
		if viewer.ShowModal()== wx.ID_OK:
			self.Destroy()
		else:
			self.selection= viewer.selection
			self.results.SetFocus()

	'''def onData(self, event: wx._core.PyEvent):
		# Translators: query evaluation binder
		# Translators: this function is not coded, thus is commented out.
		if not self.data['query']:
			return
		evaluation= 'Search query: '+self.data['query']+'\n'
#		evaluation+= [{}]
		api.copyToClip(evaluation)'''

	def onUpdate(self, event: wx._core.PyEvent):
		self._history= self.updateHistory()
		gui.messageBox(f'Items in history: {len(self._history)}. Items in session: {totalItems}.', caption= 'History Count', parent=self)

	def onExit(self, event: wx._core.PyEvent):
		self.Destroy()

	def onKey(self, event: wx._core.PyEvent):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_ESCAPE:
			self.Destroy()
		else:
			event.Skip()

	def clearResults(self):
		# Translators: clear the results gathered from the previous search, and reset the focused result
		self.resultsLabel.SetLabel(f'0 &Results Available')
		self.results.Clear()
		self.data['results'].clear()
		self.data['focusedResult']=0

	def queryResults(self, history, text):
		# Translators: compare the history to each queried result
		# Translators: text can be a string or an integer based on the user's search method.
		filter=[]
		history= [concatinateSequence(h, getSequenceIndexes()) for h in history]
		# Translators: return each history item as a concatinated string rather than a list of strings
		for n in range(0, len(history)):
			h= history[n]
			if isinstance(text, int) or self.checkFilter(h, text):
			# Translators: if text is an integer, we already have the string for this history item. Otherwise, we check if the user's search query fits the desired position in the history item.
				index= text if isinstance(text, int) else n
				self.data['results'].append({'index': index, 'sequence': self._history[index], 'text': h})
				# Translators: add this history item to our query evaluation. To refer to the current history item, we use the value of n if string, or we use the value of text if integer.
				filter.append(concatinateSequence(self._history[index], [0]))
				# Translators: also add this history item to the results list box. We add the whole concatinated string, not just the search term.
		return filter

	def checkFilter(self, h, text):
		# Translators: if the user searched by text, determine if the search term is in the desired position of the history item.
		text= text.replace('\r\n', '\n')
		h= h.replace('\r\n', '\n')
		# Translators: \r\n is used by the windows cursor, we want it to count as a new line character
		if not config.conf['speechHistory']['caseSensitive']:
			text= text.lower()
			h= h.lower()
		if h.find(text)== -1:
			if config.conf['speechHistory']['whereInString']== 'nowhere':
				return True
			else:
				return False
		if config.conf['speechHistory']['whereInString']== 'anywhere':
			return True
		if config.conf['speechHistory']['whereInString']== 'full' and h== text:
			return True
		elif config.conf['speechHistory']['whereInString']== 'beginning' and h.startswith(text):
			return True
		elif config.conf['speechHistory']['whereInString']== 'middle' and not h.startswith(text) and not h.endswith(text):
			return True
		elif config.conf['speechHistory']['whereInString']== 'end' and h.endswith(text):
			return True
		return False

class HistoryViewer(wx.Dialog):
	def __init__(self, parent, *, history, selection, index):
		self.history= {'list': None, 'index': index, 'tempSelection': [], 'data': history}
		self.selection= selection
		self.selectFunctions= {'addTemp': self.addTemp, 'clearTemp': self.clearTemp}
		super().__init__(parent, title='Speech History Viewer')
		self.makeSettings()

	def makeSettings(self):
		panel= wx.Panel(self)
		tc= wx.Notebook(panel)
		self.historyTab= HistoryPanel(tc, history= self.history, selection= self.selection, ui= self.ui)
		self.selectionTab= SelectionPanel(tc, history= self.history, selection= self.selection, ui= self.ui)
		tc.AddPage(self.historyTab, "History")
		tc.AddPage(self.selectionTab, "Selection")
		# Translators: the back button, used as cancel
		self.back= wx.Button(panel, label= '&Back to results', id=wx.ID_CANCEL)
		self.back.Bind(wx.EVT_BUTTON, self.onBack)
		# Translators: the done button, used as ok
		self.done= wx.Button(panel, label= '&Done', id=wx.ID_OK)
		self.done.Bind(wx.EVT_BUTTON, self.onDone)
		# Translators: keyboard input, for escape, used as cancel
		self.Bind(wx.EVT_CHAR_HOOK, self.onKey)
		sizer = wx.BoxSizer()
		sizer.Add(tc, 1, wx.EXPAND)
		panel.SetSizer(sizer)
		panel.SetFocus()

	# Translators: functions to be used by both tabs, not apart of this interface
	def ui(self, tab, *, function, showButtons=[], hideButtons=[], focus=None):
		if function:
			self.selectFunctions[function](tab)
		for b in showButtons:
			b.Show()
		for b in hideButtons:
			b.Hide()
		if focus:
			focus.SetFocus()

	def addTemp(self, tab):
		index= tab['list'].GetSelection()
		tab['tempSelection'].append(index)
		# Translators: update the tempSelection list with the focused index

	def clearTemp(self, tab):
		tab['tempSelection'].clear()

	# Translators: functions for this class
	def onBack(self, event: wx._core.PyEvent):
		event.Skip()

	def onDone(self, event: wx._core.PyEvent):
		event.Skip()
		self.Close()

	def onKey(self, event: wx._core.PyEvent):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_ESCAPE:
			if self.historyTab.cancel.IsShown():
				self.historyTab.onCancel(None)
				return
			if self.selectionTab.cancel.IsShown():
				self.selectionTab.onCancel(None)
				return
			self.id=wx.ID_CANCEL
		event.Skip()

class HistoryPanel(wx.Panel):
	def __init__(self, parent, *, history, selection, ui):
		self.history= history
		self.selection= selection
		self.ui= ui
		wx.Panel.__init__(self, parent)
		# Translators: the history label and list box
		self.listLabel= wx.StaticText(self, label= '&History')
		self.history['list']= wx.ListBox(self, choices= [concatinateSequence(h, [0]) for h in self.history['data']]) #style= LB_MULTIPLE might upgrade in the future!)
		# Translators: the readIndex button
		self.readIndex= wx.Button(self, label= 'Read &Index Number')
		self.readIndex.Bind(wx.EVT_BUTTON, self.onIndex)
		# Translators: the copyItem button
		self.copyItem= wx.Button(self, label= '&Copy Item To Clipboard')
		self.copyItem.Bind(wx.EVT_BUTTON, self.onCopy)
		# Translators: the start selection button
		self.start= wx.Button(self, label= 'Start Selection Here')
		self.start.Bind(wx.EVT_BUTTON, self.onStart)
		# Translators: the end selection button
		self.end= wx.Button(self, label= 'End Selection Here')
		self.end.Bind(wx.EVT_BUTTON, self.onEnd)
		self.end.Hide()
		# Translators: the position combo box
		self.positionLabel= wx.StaticText(self, label= 'Place this selection: ')
		self.position= wx.Choice(self, choices= ['at the top', 'before the current selection index', 'after the current selection index', 'at the bottom'])
		self.position.Select(self.position.FindString('at the bottom'))
		self.position.Hide()
		# Translators: the place selection button
		self.place= wx.Button(self, label= 'Place Selection')
		self.place.Bind(wx.EVT_BUTTON, self.onPlace)
		self.place.Hide()
		# Translators: the cancel selection button
		self.cancel= wx.Button(self, label= 'Cancel')
		self.cancel.Bind(wx.EVT_BUTTON, self.onCancel)
		self.cancel.Hide()
		# Translators: the refocus button
		self.refocus= wx.Button(self, label= 'Reset &Focus')
		self.refocus.Bind(wx.EVT_BUTTON, self.onRefocus)
		self.setIndex()

		# Translators: a dictionary to make it easier when managing the elements of the ui
		self.operations= {
			'mainButtons': [self.start],
			'selection': {'function': 'clearTemp', 'buttons': [self.end, self.position, self.place, self.cancel], 'focus': self.start}
		}

	def finish(self, task):
	# Translators: a shortcut for when operations finish, either by confirming or canceling the action
		task= task[task.rfind(' ')+1:].lower()
		self.ui(self.history, function= self.operations[task]['function'], showButtons= self.operations['mainButtons'], hideButtons= self.operations[task]['buttons'], focus= self.operations[task]['focus'])

	def setIndex(self):
		self.history['list'].SetSelection(self.history['index'])

	def onIndex(self, event: wx._core.PyEvent):
		LB.readIndex(self, self.history['list'])

	def onCopy(self, event: wx._core.PyEvent):
		LB.copyIndex(self, self.history['list'])

	def onStart(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.history['list']):
			return
		if len(self.selection['tempSelection'])>0:
			gui.messageBox('Please finish your selection on the other tab first.', caption= 'Invalid Operation', parent= self)
			return
		self.cancel.SetLabel('Cancel Selection')
		self.ui(self.history, function= 'addTemp', showButtons= [self.end, self.cancel], hideButtons= self.operations['mainButtons'], focus= self.end)

	def onEnd(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.history['list']):
			return
		if len(self.history['tempSelection'])==1 and self.history['list'].GetSelection()< self.history['tempSelection'][0]:
			gui.messageBox('End point can not be above start point.', caption= 'Invalid Operation', parent= self)
			return
		self.ui(self.history, function= 'addTemp', showButtons= self.operations['selection']['buttons'], hideButtons= [self.end], focus= self.position)

	def onPlace(self, event: wx._core.PyEvent):
		position= self.position.GetString(self.position.GetCurrentSelection())
		if (position== 'before the current selection index' or position== 'after the current selection index') and not LB.validIndex(self, self.selection['list']):
			return
		list= self.selection['list']
		index= self.selection['list'].GetSelection()
		modifiedIndex=0 #used for adding to the top or before the current selection index
		for t in range(self.history['tempSelection'][0], self.history['tempSelection'][1]+1):
			if position.endswith('bottom') or (position.startswith('after') and index== list.GetCount()-1):
				self.selection['data'].append(t)
				list.Append(self.history['list'].GetString(t))
			else:
				if position.startswith('after'):
					index+=1
				self.selection['data'].insert(modifiedIndex if position.endswith('top') else index+modifiedIndex if position.startswith('before') else index, t)
				list.Insert(self.history['list'].GetString(t), modifiedIndex if position.endswith('top') else index+modifiedIndex if position.startswith('before') else index)
				modifiedIndex+=1
		self.finish('selection')

	def onCancel(self, event: wx._core.PyEvent):
		self.finish(self.cancel.GetLabel())
		self.cancel.SetLabel('Cancel')

	def onRefocus(self, event: wx._core.PyEvent):
		self.setIndex()

class SelectionPanel(wx.Panel):
	def __init__(self, parent, *, history, selection, ui):
		self.history= history
		self.selection= selection
		self.ui= ui
		wx.Panel.__init__(self, parent)
		# Translators: the history label and list box
		self.listLabel= wx.StaticText(self, label= '&Selection')
		self.selection['list']= wx.ListBox(self, choices= self.selection['list'].GetItems() if isinstance(self.selection['list'], wx.ListBox) and self.selection['list'].GetCount()>0 else [])
		# Translators: the readIndex button
		self.readIndex= wx.Button(self, label= 'Read history &Index Number')
		self.readIndex.Bind(wx.EVT_BUTTON, self.onIndex)
		# Translators: the copyItem button
		self.copyItem= wx.Button(self, label= '&Copy Item To Clipboard')
		self.copyItem.Bind(wx.EVT_BUTTON, self.onCopy)
		# Translators: the start removal button
		self.start= wx.Button(self, label= 'Start removal Here')
		self.start.Bind(wx.EVT_BUTTON, self.onStart)
		# Translators: the end removal button
		self.end= wx.Button(self, label= 'End removal Here')
		self.end.Bind(wx.EVT_BUTTON, self.onEnd)
		self.end.Hide()
		# Translators: the confirm removal button
		self.confirm= wx.Button(self, label= 'Confirm Removal')
		self.confirm.Bind(wx.EVT_BUTTON, self.onConfirm)
		self.confirm.Hide()
		# Translators: the copy all to clipboard button
		self.copyAll= wx.Button(self, label= 'Copy To clipboard.')
		self.copyAll.Bind(wx.EVT_BUTTON, self.onCopyAll)
		# Translators: the item separator edit box
		self.separatorLabel= wx.StaticText(self, label= 'Symbols to separate items')
		self.separator= wx.TextCtrl(self, value= '\n', style= wx.TE_MULTILINE)
		self.separator.Hide()
		# Translators: the copy selection button
		self.clipboard= wx.Button(self, label= 'Copy Selection')
		self.clipboard.Bind(wx.EVT_BUTTON, self.onClipboard)
		self.clipboard.Hide()
		# Translators: the export button
		self.export= wx.Button(self, label= 'Export To Json File.')
		self.export.Bind(wx.EVT_BUTTON, self.onExport)
		# Translators: the text file edit box
		self.fileLabel= wx.StaticText(self, label= 'Filename')
		self.filename= wx.TextCtrl(self)
		self.filename.Hide()
		# Translators: the append item count check box
		self.append= wx.CheckBox(self, label= _('Append Item Count To Filename'))
		self.append.Hide()
		# Translators: the save file button
		self.saveFile= wx.Button(self, label= 'Save File')
		self.saveFile.Bind(wx.EVT_BUTTON, self.onFile)
		self.saveFile.Hide()
		# Translators: the cancel button
		self.cancel= wx.Button(self, label= 'Cancel')
		self.cancel.Bind(wx.EVT_BUTTON, self.onCancel)
		self.cancel.Hide()
		# Translators: the reset fields check box
		self.resetFields= wx.CheckBox(self, label= 'Reset Text Field Values After Each Use')
		self.resetFields.SetValue(config.conf['speechHistory']['resetFields'])
		self.resetFields.Bind(wx.EVT_CHECKBOX, self.onFields)
		# Translators: the clear selection button
		self.clear= wx.Button(self, label= 'Clear Selection')
		self.clear.Bind(wx.EVT_BUTTON, self.onClear)

		# Translators: a dictionary to make it easier when managing the elements of the ui
		self.operations= {
			'mainButtons': [self.start, self.copyAll, self.export, self.clear],
			'removal': {'function': 'clearTemp', 'buttons': [self.end, self.confirm, self.cancel], 'focus': self.start},
			'copy': {'function': None, 'buttons': [self.separator, self.clipboard, self.cancel], 'focus': self.copyAll},
			'export': {'function': None, 'buttons': [self.filename, self.append, self.saveFile, self.cancel], 'focus': self.export}
		}

	def finish(self, task):
	# Translators: a shortcut for when operations finish, either by confirming or canceling the action
		task= task[task.rfind(' ')+1:].lower()
		self.ui(self.selection, function= self.operations[task]['function'], showButtons= self.operations['mainButtons'], hideButtons= self.operations[task]['buttons'], focus= self.operations[task]['focus'])

	def onIndex(self, event: wx._core.PyEvent):
		LB.readIndex(self, self.selection['list'], self.selection['data'])

	def onCopy(self, event: wx._core.PyEvent):
		LB.copyIndex(self, self.selection['list'])

	def onStart(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.selection['list']):
			return
		if len(self.history['tempSelection'])>0:
			gui.messageBox('Please finish your selection on the other tab first.', caption= 'Invalid Operation', parent= self)
			return
		self.cancel.SetLabel('Cancel Removal')
		self.ui(self.selection, function= 'addTemp', showButtons= [self.end, self.cancel], hideButtons= self.operations['mainButtons'], focus= self.end)

	def onEnd(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.selection['list']):
			return
		if len(self.selection['tempSelection'])==1 and self.selection['list'].GetSelection()< self.selection['tempSelection'][0]:
			gui.messageBox('End point can not be above start point.', caption= 'Invalid Operation', parent= self)
			return
		self.ui(self.selection, function= 'addTemp', showButtons= [self.confirm], hideButtons= [self.end], focus= self.confirm)

	def onConfirm(self, event: wx._core.PyEvent):
		for t in range(0, (self.selection['tempSelection'][1]+1)-self.selection['tempSelection'][0]):
			self.selection['data'].pop(self.selection['tempSelection'][0])
			self.selection['list'].Delete(self.selection['tempSelection'][0])
		self.finish('removal')

	def onCopyAll(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.selection['list'], False):
			return
		if config.conf['speechHistory']['resetFields']:
			self.separator.SetValue('\n')
			self.separator.SetInsertionPoint(2)
		self.cancel.SetLabel('Cancel Copy')
		self.ui(self.selection, function= None, showButtons= self.operations['copy']['buttons'], hideButtons= self.operations['mainButtons'], focus= self.separator)

	def onClipboard(self, event: wx._core.PyEvent):
		copyText(self.separator.GetValue().join(self.selection['list'].GetItems()))
		self.finish('copy')

	def onExport(self, event: wx._core.PyEvent):
		if not LB.validIndex(self, self.selection['list'], False):
			return
		if config.conf['speechHistory']['resetFields']:
			self.filename.SetValue('')
		self.cancel.SetLabel('Cancel Export')
		self.ui(self.selection, function= None, showButtons= self.operations['export']['buttons'], hideButtons= self.operations['mainButtons'], focus= self.filename)

	def onFile(self, event: wx._core.PyEvent):
		text= self.filename.GetValue()
		if not text:
			gui.messageBox('Please type a filename.', caption= 'Invalid Operation', parent= self)
			return
		invalid= '\t\\/:*?"<>|'
		if not all([text.find(invalid[c])==-1 for c in range(len(invalid))]):
			gui.messageBox('A file name can\'t contain any of the following characters: tab, backslash, slash, colon, star, question, quote, less, grater, bar.', caption= 'Invalid Operation', parent= self)
			return
		exportHistory([self.history['data'][h] for h in self.selection['data']], text, self.append.GetValue())
		self.finish('export')

	def onCancel(self, event: wx._core.PyEvent):
		self.finish(self.cancel.GetLabel())
		self.cancel.SetLabel('Cancel')

	def onFields(self, event: wx._core.PyEvent):
		config.conf['speechHistory']['resetFields']= self.resetFields.GetValue()

	def onClear(self, event: wx._core.PyEvent):
		self.selection['list'].Clear()
		self.selection['data'].clear()

class SearchOptions(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title='Speech History Search Options')
		self.makeSettings()

	def makeSettings(self):
		# Translators: the preference to choose the way you search
		self.searchByLabel= wx.StaticText(self, label= '&Search By')
		self.searchBy= wx.Choice(self, choices= ['text', 'index'])
		self.searchBy.Select(self.searchBy.FindString(config.conf['speechHistory']['searchBy']))
		# Translators: the preference to choose where the query should be in the results
		self.whereInStringLabel= wx.StaticText(self, label= '&Where In String')
		self.whereInString= wx.Choice(self, choices= ['anywhere', 'full', 'beginning', 'middle', 'end', 'nowhere'])
		self.whereInString.Select(self.whereInString.FindString(config.conf['speechHistory']['whereInString']))
		# Translators: the preference to choose if text searches are case sensitive
		self.caseSensitive= wx.CheckBox(self, label=_('&Case Sensitive'))
		self.caseSensitive.SetValue(config.conf['speechHistory']['caseSensitive'])
		# Translators: the preference to queryResultsAsYouType
		self.queryResultsAsYouType= wx.CheckBox(self, label=_('Query &Results As You Type'))
		self.queryResultsAsYouType.SetValue(config.conf['speechHistory']['queryResultsAsYouType'])
		# Translators: the preference to choose which parts of the sequence to search
		self.sequenceIndexesLabel= wx.StaticText(self, label= 'Sequence &indexes to search or exclude. Use 0 for all indexes. Use an exclamation at the beginning to exclude. Use space to separate indexes.')
		self.sequenceIndexes= wx.TextCtrl(self)
		self.sequenceIndexes.SetValue(('!' if config.conf['speechHistory']['inverseIndexes'] else '')+config.conf['speechHistory']['sequenceIndexes'])
		# Translators: the ok button
		self.ok= wx.Button(self, label= 'Ok', id=wx.ID_OK)
		self.ok.Bind(wx.EVT_BUTTON, self.onOk)
		# Translators: the cancel button
		self.cancel= wx.Button(self, label= 'Cancel', id=wx.ID_CANCEL)
		self.cancel.Bind(wx.EVT_BUTTON, self.onCancel)
		# Translators: keyboard input, for escape, used as cancel
		self.Bind(wx.EVT_CHAR_HOOK, self.onKey)
		self.ok.SetFocus()
		self.searchBy.SetFocus()
		# Translators: for some strange reason, we can only use enter to press ok once the ok button has been focused. So we give it temporary focus during initialization

	def onCancel(self, event):
		event.Skip()

	def onOk(self, event):
		indexes= self.sequenceIndexes.GetValue()
		inverse=False
		if indexes.startswith('!'):
			indexes= indexes[1:]
			inverse=True
		if not all([i.isdigit() for i in indexes.split(' ')]):
			gui.messageBox('Numbers only. Parse indexes with space.', caption= _('Invalid Sequence Selection'), parent= self)
			return
		config.conf['speechHistory']['searchBy'] = self.searchBy.GetString(self.searchBy.GetCurrentSelection())
		config.conf['speechHistory']['whereInString'] = self.whereInString.GetString(self.whereInString.GetCurrentSelection())
		config.conf['speechHistory']['caseSensitive'] = self.caseSensitive.GetValue()
		config.conf['speechHistory']['queryResultsAsYouType'] = self.queryResultsAsYouType.GetValue()
		config.conf['speechHistory']['sequenceIndexes'] = indexes
		config.conf['speechHistory']['inverseIndexes'] = inverse
		event.Skip()

	def onKey(self, event: wx._core.PyEvent):
		event.Skip()
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_ESCAPE:
			self.id=wx.ID_CANCEL

# Translators: global functions

def copyText(text):
	if config.conf['speechHistory']['trimWhitespaceFromStart']:
		text = text.lstrip()
	if config.conf['speechHistory']['trimWhitespaceFromEnd']:
		text = text.rstrip()
	if api.copyToClip(text):
		tones.beep(1500, 120)

def getSequenceIndexes():
	# Translators: converts the sequence option from a string into an integer list.
	return [int(i) for i in config.conf['speechHistory']['sequenceIndexes'].split(' ')]

def concatinateSequence(sequence, indexes):
# Translators: turn sequences into a combined string
	# Translators: indexes: the parts of the sequence to concatinate. Value 0 represents all.
	return '  '.join([str(sequence[i]) for i in range(len(sequence)) if 0 in indexes or (not config.conf['speechHistory']['inverseIndexes'] and i+1 in indexes) or (config.conf['speechHistory']['inverseIndexes'] and i+1 not in indexes)])

def dequeToList(deque, reverse, start, end):
	nowList=[]
	nowList[:]= list(deque)[start:end]
	if reverse:
		nowList.reverse()
	return nowList

def cycleRemainder():
	return totalItems%config.conf['speechHistory']['maxHistoryLength']

def exportHistory(history, path=None, appendItemCount=True, start=0, end=None):
	if not os.path.exists(f'{folder}/speechLogs'):
		os.mkdir(f'{folder}/speechLogs')
	if not os.path.exists(f'{folder}/speechLogs/autoExport'):
		os.mkdir(f'{folder}/speechLogs/autoExport')
	if not os.path.exists(f'{folder}/speechLogs/custom'):
		os.mkdir(f'{folder}/speechLogs/custom')
	t= time.localtime(time.time())
	info=[]
	for u in [t.tm_mon, t.tm_mday, t.tm_min, t.tm_sec]:
		info.append(('0' if u<10 else '')+str(u))
	thisDate= f'{t.tm_year}-{info[0]}-{info[1]}'
	thisTime= f'{t.tm_hour}-{info[2]}-{info[3]}'
	if end is None:
		end= len(history)
	if isinstance(history, deque):
		history = dequeToList(history, True, start, end)
	itemCount= len(history)
	data= {
		'date': thisDate,
		'time': thisTime,
		'max length': config.conf['speechHistory']['maxHistoryLength'],
		'item count': itemCount,
		'item count in session': totalItems,
		'history': [[str(i) for i in h] for h in history]
	}
	if path is None:
		path= f'autoExport/{thisDate} At {thisTime}'
	else:
		path= f'custom/{path}'
	if appendItemCount:
		path+= f'; {itemCount} Item'+('s' if itemCount!= 1 else '')
	saveJson(data, f'{folder}/speechLogs/{path}')

def saveJson(dictionary, path, ext='json', indent= ' '):
	f = open(f'{path}.{ext}', 'w')
	json.dump(dictionary, f, indent=indent)
	f.close()

def loadJson(path, ext='json'):
	with open(f'{path}.{ext}') as f:
		try:
			dictionary= json.load(f)
		except json.decoder.JSONDecodeError:
			gui.messageBox('Failed to load dictionary!', caption= 'Dictionary Error', parent=None)
		f.close()
	return dictionary