#!/usr/bin/env python3

import logging
logging.basicConfig(format="[%(asctime)s] (%(name)s) %(levelname)s: %(message)s")

import datetime
import random
import re

import astm
import sofia
import pyodbc
import windoc_interface.klein_tools as klein_tools

import config

from astm.omnilab.server import RecordsDispatcher
from astm.constants import EOT, STX, NAK

_log = logging.getLogger('Dispatcher')
_log.setLevel('INFO')

_db = pyodbc.connect("Driver={Pervasive ODBC Interface};DBQ=DOC;ServerName=10.238.80.100:1583")
klein_tools.init(_db)

_log.info("Hello World")
class Dispatcher(astm.server.BaseRecordsDispatcher):

    def __init__(self, *args, **kwargs):
        super(Dispatcher, self).__init__(*args, **kwargs)
        self.log = _log.getChild(hex(random.randint(0, 16**8))[2:])
        self.log.info("Created Dispatcher instance")
        self.wrappers = sofia.WRAPPER_DICT
        self.state = 'start'

    def on_header(self, record):
        assert self.state == 'start', "unexpected 'H' record"

        self.header = record
        self.results = []
        self.private = False
        self.log.info("Received H record. Allocating empty result set")

        self.state = 'ready'

    def on_patient(self, record):
        assert self.state == 'ready', "unexpected 'P' record"

        istr = klein_tools.Intern.insanify(re.sub(r'[^0-9]+', '', '0'+record.practice_id))
        self.patient_record = record
        self.current_patient = klein_tools.Intern(istr)
        self.log.info("Received P record (%s)", istr)

        self.state = 'ready_for_order'

    def on_order(self, record):
        assert self.state == 'ready_for_order', "unexpected 'O' record"

        self.log.info("Received O record")
        self.current_order = record
        if record.sample_id and record.sample_id.lower() == 'privat'[:len(record.sample_id)]:
            self.private = True
            self.log.info("Order has tag PRIVATE (%s)", record.sample_id)

        self.state = 'ready_for_result'

    def on_comment(self, record):
        self.log.info("ignoring comment record")

    def on_result(self, record):
        assert self.state == 'ready_for_result', "unexpected 'R' record"

        self.results.append(record)
        self.log.info("Received R record %s=%s, added to result set", record.test.analyte_name, record.value)

    def on_terminator(self, record):
        assert self.state == 'ready_for_result', "unexpected 'L' record"

        self.log.info("Received L record, committing result set")
        if len(self.results) == 0:
            self.log.info("Result set empty")
            self.state = 'start'
            return

        self.log.info("Result set has entries, checking for calibration")

        if self.results[0].test.analyte_name in [ 'CB CASS', 'POS', 'NEG' ] and not self.current_patient.exists():
            self.log.warning("Ignoring results that look like calibration, and patient does not exist")
            self.state = 'start'
            return

        self.log.info("Checking if patient exists")
        assert self.current_patient.exists(), f"patient {self.current_patient.Intern} not found"

        hdatum = self.header.timestamp.strftime("%Y%m%d")
        datum = datetime.datetime.now().strftime("%Y%m%d")

        c = _db.cursor()

        self.log.info("Processing result set")
        for res in self.results:
            rdatum = res.completed_at.strftime("%Y%m%d")

            if (self.header.timestamp - res.completed_at).total_seconds() > config.ignore_timeout:
                self.log.warning("Ignoring result from %s", res.completed_at)
                continue

            labor = klein_tools.LabTemplate(res.test.analyte_name)

            skip_service = False
            skip_labor = False

            if not hasattr(labor, 'service'):
                skip_service = True
                self.log.info("LabTemplate has no service registered")

            if self.private:
                skip_service = True

            if not skip_service:
                ktab = self.current_patient.kassen_ref()
                if res.test.analyte_name == 'SARS' and klein_tools.guess_if_positive(res.value):
                    self.log.info("Detected positive SARS test, overriding Posnummer='COVT1'")
                    pos = 'COVT1'
                else:
                    pos = ktab.position_from_service(labor.service).strip()

                clock = res.completed_at
                eintr = klein_tools.Kassenkartei.leistung(datum=rdatum, pos=pos, cnt=1, kasse=ktab.num, clock=clock)
                notiz_eintr = clock.strftime("%H:%M") + " Automatische Eintragung durch Sofia Gerät erfolgreich"

                c.execute("SELECT Count(*) FROM Kassenkartei WHERE Intern = ? AND Datum = ? AND Eintragung = ?", self.current_patient.Intern, rdatum, eintr)
                rr = c.fetchone()
                if rr[0] > 0:
                    self.log.warning("Duplicate: Intern='%s' Datum='%s' Eintrag='%s' ignored", self.current_patient.Intern, rdatum, eintr)
                    skip_service = True
                    skip_labor = True
            if skip_labor:
                self.log.info("Not creating Labor entry")
            else:
                c.execute("INSERT INTO Labor (Intern, Datum, Gruppe, Kurzbezeichnung, Wert) VALUES (?,?,?,?,?)", self.current_patient.Intern, rdatum, labor.group, labor.lab, res.value)
                self.log.info("INSERT INTO Labor: Intern='%s' Datum='%s' Kurz='%s' Wert='%s'", self.current_patient.Intern, rdatum, labor.lab, res.value)

            if skip_service:
                if self.private:
                    self.log.info("Not creating Kassenkartei entries, is tagged private")
                else:
                    self.log.info("Not creating Kassenkartei entries")
            else:
                c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, rdatum, 'L', 'XX', eintr)
                self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s', Eintrag='%s'", self.current_patient.Intern, rdatum, 'L', eintr)
                c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, rdatum, 'T', 'XX', notiz_eintr)
                self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s', Eintrag='%s'", self.current_patient.Intern, rdatum, 'T', notiz_eintr)

            c.commit()
            self.log.info("Record committed")

        c.close()

        self.state = 'start'

s = astm.server.Server(dispatcher=Dispatcher, host='0.0.0.0', port=1245)
s.serve_forever()
