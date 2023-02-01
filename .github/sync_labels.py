#!/usr/bin/python
# -*- coding: utf-8 -*-

r"""
Python script to sync labels that are migrated from Trac selection lists.
"""

##############################################################################
#       Copyright (C) 2023 Sebastian Oehms <seb.oehms@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#                  http://www.gnu.org/licenses/
##############################################################################

import os
import sys
import json
from enum import Enum

class SelectionList(Enum):
    """
    Abstract Enum for selection lists.
    """
    def succ(self):
        """
        Return the successor of `self`.
        """
        l = list(self.__class__)
        i = l.index(self)
        if i + 1 == len(l):
            if i:
                return l[i-1]
            else:
                return None
        return l[i+1]

class Priority(SelectionList):
    """
    Enum for priority lables.
    """
    blocker = 'p: blocker /1'
    critical = 'p: critical /2'
    major = 'p: major /3'
    minor = 'p: minor /4'
    trivial = 'p: trivial /5'

class State(SelectionList):
    """
    Enum for state lables.
    """
    closed = 'closed'
    positive_review = 'positive review'
    needs_review = 'needs review'
    needs_work = 'needs work'
    needs_info = 'needs info'
    new = 'new'

class IssueType(SelectionList):
    """
    Enum for type lables.
    """
    bug = 'bug'
    enhancement = 'enhancement'
    task = 'task'

def selection_list(label):
    """
    Return the selection list to which `label` belongs to.
    """
    for sel_list in [Priority, State, IssueType]:
        for item in sel_list:
            if label == item.value:
                return sel_list
    return None

class GhLabelSynchronizer:
    """
    Handler for access to GitHub issue via the `gh` in the bash command line
    of the GitHub runner.
    """
    def __init__(self, url, labels):
        """
        Python constructor sets the issue / PR url and list of active labels.
        """
        self._url = url
        self._labels = labels
        number = os.path.basename(url)
        self._pr = True
        self._issue = 'pull request #%s' % number
        if url.rfind('issue') != -1:
            self._issue = 'isuue #%s' % number
            self._pr = False

    def active_partners(self, label):
        """
        Return the list of other labels from the selection list
        of the given one that are already present on the issue / PR.
        """
        sel_list = selection_list(label)
        val = [i.value for i in sel_list]
        return [l for l in self._labels if l in val and not l == label]

    def edit(self, arg, option):
        """
        Perform a system call to `gh` to edit an issue or PR.
        """
        issue = 'issue'
        if self._pr:
            issue = 'pr'
        cmd = 'gh %s edit %s %s "%s"' % (issue, self._url, option, arg)
        os.system(cmd)

    def add_comment(self, text):
        """
        Perform a system call to `gh` to add a comment to an issue or PR.
        """
        issue = 'issue'
        if self._pr:
            issue = 'pr'
        cmd = 'gh %s comment %s -b "%s"' % (issue, self._url, text)
        os.system(cmd)
        print('Comment %s added to %s' % (text, self._issue))

    def add_label(self, label):
        """
        Add the given label to the issue or PR.
        """
        if not label in self._labels:
            self.edit(label, '--add-label')
            print('Label %s added to %s' % (label, self._issue))

    def add_default_label(self, label):
        """
        Add the given label if there is no active partner.
        """
        if not self.active_partners(label):
            self.add_label(label)

    def on_label_add(self, label):
        """
        Check if the given label belongs to a selection list.
        If so, remove all other labels of that list.
        """
        sel_list = selection_list(label)
        if not sel_list:
            return
        item = sel_list(label)
        if sel_list is State and self._pr:
            if item not in [State.needs_info, State.needs_review]:
                self.add_comment('Label can not be added. Please use the corresponding functionality of GitHub')
                self.remove_label(label)
                return

        for other in sel_list:
            if other != item:
                self.remove_label(other.value)

    def select_label(self, label):
        """
        Add the given label and remove all others.
        """
        self.add_label(label)
        self.on_label_add(label)

    def remove_label(self, label):
        """
        Remove the given label from the issue or PR of the handler.
        """
        if label in self._labels:
            self.edit(label, '--remove-label')
            print('Label %s removed from %s' % (label, self._issue))

    def on_label_remove(self, label):
        """
        Check if the given label belongs to a selection list. If so, reject
        the removement in case it represents the stat of a PR.  In all other
        cases add the successor of the label except if there is none or there
        exists another label of the corresponding list.
        """
        sel_list = selection_list(label)
        if not sel_list:
            return
        item = sel_list(label)
        if sel_list is State and self._pr:
            if item in [State.positive_review, State.needs_work, State.close]:
                self.add_comment('Label can not be removed. Please use the corresponding functionality of GitHub')
                self.select_label(label)
                return

        if not self.active_partners(label):
            succ = sel_list(label).succ()
            if succ:
                # add the next weaker label
                self.select_label(succ.value)
            else:
                self.add_comment('Label can not be removed since there is no replacement')
                self.select_label(label)
            

###############################################################################
# Main
###############################################################################
cmdline_args = sys.argv[1:]
print('cmdline_args', len(cmdline_args), cmdline_args)
if len(cmdline_args) < 6:
    print('Need 6 arguments: action, url, label, state, issue_labels, pr_labels' )
    exit
else:
    action, url, label, state, issue_labels, pr_labels = cmdline_args

labels = json.loads(issue_labels)
if not labels:
    labels = json.loads(pr_labels)

base_url = url
for i in range(3): base_url = os.path.dirname(base_url)
print("action", action)
print("url", url)
print("label", label)
print("state", state)
print("labels", labels)
print("base_url", base_url)

gh = GhLabelSynchronizer(url, labels)


if action == 'opened':
    gh.add_default_label(Priority.major.value)
    gh.add_default_label(State.new.value)
    gh.add_default_label(IssueType.task.value)

if action == 'labeled':
    gh.on_label_add(label)

if action == 'unlabeled':
    gh.on_label_remove(label)

if action == 'submitted':
    if state == 'approved':
        gh.select_label(State.positive_review.value)

    if state == 'changes_requested':
        gh.select_label(State.needs_work.value)

    if state == 'commented':
        # just for testing
        gh.select_label(State.needs_work.value)

if action in ('review_requested', 'ready_for_review'):
    gh.select_label(State.needs_review.value)
