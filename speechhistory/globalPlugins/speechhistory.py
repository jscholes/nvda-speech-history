# NVDA Add-on: Speech History
# Copyright (C) 2012 Tyler Spivey
# Copyright (C) 2015-2017 James Scholes
# This add-on is free software, licensed under the terms of the GNU General Public License (version 2).
# See the file LICENSE for more details.

import api
import globalPluginHandler
from queueHandler import eventQueue, queueFunction
import speech
import tones
import ui

oldSpeak = speech.speak
oldSpeakSpelling = speech.speakSpelling
data = ''
history = []
history_pos = 0

def append_to_history(string):
    global history, history_pos
    if len(history) == 100:
        history.pop()
    history.insert(0, string)
    history_pos = 0

def mySpeak(sequence, *args, **kwargs):
    global data
    text = u''.join([x for x in sequence if isinstance(x, basestring)])
    if text:
        data = text
        oldSpeak(sequence, *args, **kwargs)
        queueFunction(eventQueue, append_to_history, text)

def mySpeakSpelling(text, *args, **kwargs):
    global data
    if text:
        data = text
    oldSpeakSpelling(text, *args, **kwargs)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        global oldSpeak, oldSpeakSpelling
        oldSpeak = speech.speak
        speech.speak = mySpeak
        oldSpeakSpelling = speech.speakSpelling
        speech.speakSpelling = mySpeakSpelling

    def script_copyLast(self, gesture):
        if api.copyToClip(history[history_pos]):
            tones.beep(1500, 120)

    def script_prevString(self, gesture):
        global history_pos
        history_pos += 1
        if history_pos > len(history) - 1:
            tones.beep(200, 100)
            history_pos -= 1

        oldSpeak([history[history_pos]])

    def script_nextString(self, gesture):
        global history_pos
        history_pos -= 1
        if history_pos < 0:
            tones.beep(200, 100)
            history_pos += 1

        oldSpeak([history[history_pos]])

    def terminate(self):
        speech.speak = oldSpeak

    __gestures = {
        "kb:f12":"copyLast",
        "kb:shift+f11":"prevString",
        "kb:shift+f12":"nextString",
    }
