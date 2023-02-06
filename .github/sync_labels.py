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
from logging import info, warning, getLogger, INFO
from json import loads
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
    positive_review = 's: positive review'
    needs_review = 's: needs review'
    needs_work = 's: needs work'
    needs_info = 's: needs info'

class IssueType(SelectionList):
    """
    Enum for type lables.
    """
    bug = 't: bug'
    enhancement = 't: enhancement'
    performance = 't: performance'
    refactoring = 't: refactoring'
    feature = 't: feature'
    tests = 't: tests'

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
    def __init__(self, url):
        """
        Python constructor sets the issue / PR url and list of active labels.
        """
        self._url = url
        self._labels = None
        self._draft = None
        self._open = None
        number = os.path.basename(url)
        self._pr = True
        self._issue = 'pull request #%s' % number
        if url.rfind('issue') != -1:
            self._issue = 'issue #%s' % number
            self._pr = False
        info('Create label handler for %s' % self._issue)


    def is_pull_request(self):
        """
        Return if we are treating a pull request.
        """
        return self._pr

    def view(self, key):
        """
        Return data obtained from `gh` command `view`.
        """
        issue = 'issue'
        if self._pr:
            issue = 'pr'
        cmd = 'gh %s view %s --json %s' % (issue, self._url, key)
        from subprocess import check_output
        return loads(check_output(cmd, shell=True))

    def is_open(self):
        """
        Return if the issue res. PR is open.
        """
        if self._open is not None:
            return self._open
        if self.view('state')['state'] == 'OPEN':
            self._open = True
        else:
            self._open = False
        return self._open

    def is_draft(self):
        """
        Return if the PR is a draft.
        """
        if self._draft is not None:
            return self._draft
        if self.is_pull_request():
            self._draft = self.view('isDraft')['isDraft']
        else:
            self._draft = False
        return self._draft

    def get_labels(self):
        """
        Return the list of labels of the issue resp. PR.
        """
        if self._labels is not None:
            return self._labels
        data = self.view('labels')['labels']
        self._labels = [l['name'] for l in data]
        info('List of labels for %s: %s' % (self._issue, self._labels))
        return self._labels

    def edit(self, arg, option):
        """
        Perform a system call to `gh` to edit an resp. PR.
        """
        issue = 'issue'
        if self._pr:
            issue = 'pr'
        cmd = 'gh %s edit %s %s "%s"' % (issue, self._url, option, arg)
        os.system(cmd)

    def active_partners(self, label):
        """
        Return the list of other labels from the selection list
        of the given one that are already present on the issue / PR.
        """
        sel_list = selection_list(label)
        val = [i.value for i in sel_list]
        return [l for l in self.get_labels() if l in val and not l == label]

    def add_comment(self, text):
        """
        Perform a system call to `gh` to add a comment to an issue or PR.
        """
        issue = 'issue'
        if self._pr:
            issue = 'pr'
        cmd = 'gh %s comment %s -b "%s"' % (issue, self._url, text)
        os.system(cmd)
        info('Add comment to %s: %s' % (self._issue, text))

    def add_label(self, label):
        """
        Add the given label to the issue or PR.
        """
        if not label in self.get_labels():
            self.edit(label, '--add-label')
            info('Add label to %s: %s' % (self._issue, label))

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

        if label not in self.get_labels():
            # this is possible if two labels of the same selection list
            # have been added in one step (via multiple selection in the
            # pull down menue). In this case `label` has been removed
            # on the `on_label_add` of the first of the two labels
            partn = self.active_partners(label)
            if partn:
                self.add_comment('Label *%s* can not be added due to *%s*!' % (label, partn[0]))
            else:
                warning('Label %s of %s not found!' % (label, self._issue))
            return

        item = sel_list(label)
        if sel_list is State and self._pr:
            if not self.is_pull_request():
                if item != State.needs_info:
                    self.add_comment('Label *%s* can not be added to an issue. Please use it on the corresponding PR' % label)
                    self.remove_label(label)
                    return

            if item in [State.positive_review, State.needs_work]:
                self.add_comment('Label *%s* can not be added. Please use the corresponding functionality of GitHub' % label)
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
        if label in self.get_labels():
            self.edit(label, '--remove-label')
            info('Remove label from %s: %s' % (self._issue, label))

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

        if label in self.get_labels():
            # this is possible if two labels of the same selection list
            # have been removed in one step (via multiple selection in the
            # pull down menue). In this case `label` has been added
            # on the `on_label_remove` of the first of the two labels.
            partn = self.active_partners(label)
            if not partn:
                self.add_comment('Label *%s* can not be removed (last one of list)!' % label)
            else:
                self.on_label_add(partn[0])
            return

        item = sel_list(label)
        if sel_list is State and self._pr:
            if item in [State.positive_review, State.needs_work]:
                self.add_comment('Label *%s* can not be removed. Please use the corresponding functionality of GitHub' % label)
                self.select_label(label)
                return

        if not self.active_partners(label):
            succ = sel_list(label).succ()
            if succ:
                # add the next weaker label
                self.select_label(succ.value)
            else:
                self.add_comment('Label *%s* can not be removed since there is no replacement' % label)
                self.select_label(label)
            

###############################################################################
# Main
###############################################################################
cmdline_args = sys.argv[1:]

getLogger().setLevel(INFO)
info('cmdline_args (%s) %s' % (len(cmdline_args), cmdline_args))

if len(cmdline_args) < 4:
    print('Need 4 arguments: action, url, label, rev_state' )
    exit
else:
    action, url, label, rev_state = cmdline_args

info('action: %s' % action)
info('url: %s' % url)
info('label: %s' % label)
info('rev_state: %s' % rev_state)

gh = GhLabelSynchronizer(url)

if action == 'opened':
    gh.add_default_label(Priority.major.value)
    gh.add_default_label(IssueType.enhancement.value)
    if gh.is_pull_request():
        if not gh.is_draft():
            gh.add_default_label(State.needs_review.value)

if action == 'reopened':
    if gh.is_pull_request():
        if not gh.is_draft():
            gh.add_default_label(State.needs_review.value)

if action == 'closed':
    for lab in State:
        gh.remove_label(lab.value)

if action == 'labeled':
    gh.on_label_add(label)

if action == 'unlabeled':
    gh.on_label_remove(label)

if action == 'submitted':
    if rev_state == 'approved':
        gh.select_label(State.positive_review.value)

    if rev_state == 'changes_requested':
        gh.select_label(State.needs_work.value)

    if rev_state == 'commented':
        # just for testing
        gh.select_label(State.needs_work.value)

if action in ('review_requested', 'ready_for_review'):
    gh.select_label(State.needs_review.value)
