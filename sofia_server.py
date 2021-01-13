#!/usr/bin/env python3

import logging
logging.basicConfig(format="[%(asctime)s] %(levelname)s: %(message)s")

import datetime

import astm
import sofia
import pyodbc
import klein_tools

from astm.omnilab.server import RecordsDispatcher
from astm.constants import EOT, STX, NAK

_log = logging.getLogger('Dispatcher')
_log.setLevel('INFO')

_db = pyodbc.connect("Driver={Pervasive ODBC Interface};DBQ=DOC;ServerName=10.238.80.100:1583")
klein_tools.init(_db)

class Dispatcher(astm.server.BaseRecordsDispatcher):

    def __init__(self, *args, **kwargs):
        super(Dispatcher, self).__init__(*args, **kwargs)
        self.wrappers = sofia.WRAPPER_DICT
        self.state = 'start'

    def on_header(self, record):
        if self.state != 'start':
            _log.warning("unexpected 'H' record, discarding")
            return
        self.header = record
        self.state = 'ready'

    def on_patient(self, record):
        if self.state != 'ready':
            _log.warning("unexpected 'P' record, commiting old result and continuing with new patient")
        istr = klein_tools.Intern.insanify(record.practice_id)
        pat = klein_tools.Intern(istr)
        if not pat.exists():
            raise ValueError("Patient mit Intern '%s' existiert nicht!" % record.practice_id)
        self.current_patient = pat
        self.state = 'ready_for_order'

    def on_order(self, record):
        if self.state != 'ready_for_order':
            _log.warning("unexpected 'O' record, overriding current")
        self.current_order = record
        self.labor = klein_tools.Labor(record.test)
        self.state = 'ready_for_result'

    def on_comment(self, record):
        _log.info("ignoring comment record")

    def on_result(self, record):
        if self.state != 'ready_for_result':
            _log.warning("unexpected 'R' record, continuing anyway")
        _log.info("INSERT INTO Labor (Intern, Datum, Gruppe, Kurzbezeichnung, Wert) VALUES (?,?,?,?,?)", self.current_patient.Intern, datetime.datetime.now().strftime("%Y%m%d"), self.labor.group, self.labor.lab, record.value)
        self.state = 'ready'

    def on_terminator(self, record):
        self.state = 'start'

s = astm.server.Server(dispatcher=Dispatcher)
s.serve_forever()
