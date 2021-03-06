#!/usr/bin/env python3

import logging
logging.basicConfig(format="[%(asctime)s] (%(name)s) %(levelname)s: %(message)s")

import datetime
import random
import re
import os
import signal

import astm
import sofia
import pyodbc
import windoc_interface.klein_tools as klein_tools
import windoc_interface.klein_tools.db as klein_tools_db
import windoc_interface.klein_tools.kassenkartei as kassenkartei

import config

from astm.omnilab.server import RecordsDispatcher
from astm.constants import ENQ, EOT, STX, NAK, ACK

_log = logging.getLogger()
_log.setLevel('INFO')

_pool = klein_tools_db.Pool(os.environ['WINDOC_DSN'])

def SIGTERM(*args, **kwargs):
    _log.info("SIGTERM received, raising SystemExit")
    raise SystemExit()
signal.signal(signal.SIGTERM, SIGTERM)

with _pool.open() as db:
    c = db.cursor()
    c.execute('SELECT 1')

_log.info("Sofia Server successfully started. Listening for incoming connections ... ")

class RequestHandler(astm.server.RequestHandler):

    def __init__(self, *args, **kwargs):
        super(RequestHandler, self).__init__(*args, **kwargs)

        self.log = logging.getLogger('RequestHandler.' + self.dispatcher.identifier)
        self.log.setLevel('INFO')

        if os.path.exists('/data'):
            self.dump = open('/data/' + self.dispatcher.identifier, 'wb')
        else:
            self.dump = open('/dev/null', 'wb')

        self.dispatcher.dump = self.dump
        self.log.info("Ready")

    def on_enq(self):
        self.dump.write(("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"), repr(ENQ))).encode('UTF-8'))
        return super().on_enq()

    def on_ack(self):
        self.dump.write(("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"), repr(ACK))).encode('UTF-8'))
        return super().on_ack()

    def on_nak(self):
        self.dump.write(("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"), repr(NAK))).encode('UTF-8'))
        return super().on_nak()

    def on_eot(self):
        self.dump.write(("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"), repr(EOT))).encode('UTF-8'))
        return super().on_eot()

    def close(self):
        self.dump.close()
        return super().close()

class Dispatcher(astm.server.BaseRecordsDispatcher):

    def __init__(self, *args, **kwargs):
        super(Dispatcher, self).__init__(*args, **kwargs)
        self.identifier = hex(random.randint(0, 16**8))[2:]
        self.log = logging.getLogger('Dispatcher.' + self.identifier)
        self._db = _pool.open()
        self.log.info("Created Dispatcher instance")
        self.wrappers = sofia.WRAPPER_DICT
        self.state = 'start'

    def __call__(self, msg):
        self.dump.write(("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"), repr(msg))).encode('UTF-8'))
        return super().__call__(msg)

    def on_header(self, record):
        assert self.state == 'start', "unexpected 'H' record"

        self.header = record
        self.results = []
        self.private = False
        self.log.info("Received H record. Allocating empty result set")

        self.state = 'ready'

    def on_patient(self, record):
        assert self.state == 'ready', "unexpected 'P' record"

        istr = klein_tools.format_intern(re.sub(r'[^0-9]+', '', '0'+record.practice_id))
        self.patient_record = record
        self.current_patient = self._db.Intern(istr)
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

        if ((self.results[0].test.analyte_name == 'CB CASS' and self.results[0].value == 'passed') or
                (self.results[0].test.analyte_name == 'POS' and self.results[0].value == 'passed') or
                (self.results[0].test.analyte_name == 'NEG' and self.results[0].value == 'passed')):
            self.log.info("Ignoring calibration results")
            self.state = 'start'
            return

        self.log.info("Opening DB connection")
        with self._db:
            self.log.info("Checking if patient exists")
            assert self.current_patient.exists(), f"patient {self.current_patient.Intern} not found"

            hdatum = self.header.timestamp.strftime("%Y%m%d")
            datum = datetime.datetime.now().strftime("%Y%m%d")
            logpre = datetime.datetime.now().strftime('[%H:%M]') + " Sofia"

            c = self._db.cursor()

            self.log.info("Processing result set")

            kartei_entries = []
            labor_entries = []
            for res in self.results:
                rdatum = res.completed_at.strftime("%Y%m%d")

                if (self.header.timestamp - res.completed_at).total_seconds() > config.ignore_timeout:
                    self.log.warning("Ignoring result from %s", res.completed_at)
                    continue

                labor = self._db.LabTemplate(res.test.analyte_name)

                skip_service = False
                skip_labor = False

                if not hasattr(labor, 'service'):
                    skip_service = True
                    self.log.info("LabTemplate has no service registered")

                if self.private:
                    skip_service = True

                try:
                    if not skip_service:
                        ktab = self.current_patient.kassen_ref()
                        if res.test.analyte_name == 'SARS' and klein_tools.guess_if_positive(res.value):
                            self.log.info("Detected positive SARS test, overriding Posnummer='COVT1'")
                            pos = 'COVT1'
                        else:
                            pos = ktab.position_from_service(labor.service).strip()

                        clock = res.completed_at
                        eintr = kassenkartei.leistung(datum=rdatum, pos=pos, cnt=1, kasse=ktab.num, clock=clock)

                        c.execute("SELECT Count(*) FROM Kassenkartei WHERE Intern = ? AND Datum = ? AND Eintragung = ?", self.current_patient.Intern, rdatum, eintr)
                        rr = c.fetchone()
                        if rr[0] > 0:
                            self.log.warning("Duplicate: Intern='%s' Datum='%s' Eintrag='%s' ignored", self.current_patient.Intern, rdatum, eintr)
                            skip_service = True
                            skip_labor = True
                except Exception as ex:
                    self.log.warning("Could not create Kassenkartei entry: " + repr(ex))
                    # msg = "Auto-Sofia: Fehler beim Eintragen einer Leistung (Fehler-Code: %s)" % self.identifier
                    # c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, datum, 'T', '', msg)
                    # c.commit()
                    # self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s' Eintragung='%s'", self.current_patient.Intern, datum, 'T', msg)
                    skip_service = True

                if skip_labor:
                    self.log.info("Not creating Labor entry")
                else:
                    c.execute("INSERT INTO Labor (Intern, Datum, Gruppe, Kurzbezeichnung, Wert) VALUES (?,?,?,?,?)", self.current_patient.Intern, rdatum, labor.group, labor.lab, res.value)
                    self.log.info("INSERT INTO Labor: Intern='%s' Datum='%s' Kurz='%s' Wert='%s'", self.current_patient.Intern, rdatum, labor.lab, res.value)
                    labor_entries.append((res.completed_at, labor.lab, res.value))

                if skip_service:
                    if self.private:
                        self.log.info("Not creating Kassenkartei entries, is tagged private")
                    else:
                        self.log.info("Not creating Kassenkartei entries")
                else:
                    c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, rdatum, 'L', '', eintr)
                    self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s', Eintrag='%s'", self.current_patient.Intern, rdatum, 'L', eintr)
                    kartei_entries.append((res.completed_at, pos))

                c.commit()
                self.log.info("Record committed")

            
            if len(labor_entries) > 0:           
                notiz_eintr = "%s: Labor %s (Test vom %s Uhr)" % (logpre, ','.join(e[1] for e in labor_entries), labor_entries[0][0].strftime("%d.%m.%Y, %H:%M"))
                c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, datum, 'T', '', notiz_eintr)
                c.commit()
                self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s', Eintrag='%s'", self.current_patient.Intern, datum, 'T', notiz_eintr)

            if len(kartei_entries) > 0:
                notiz_eintr = "%s: Leistung %s" % (logpre, ','.join(e[1] for e in kartei_entries))
                c.execute("INSERT INTO Kassenkartei (Intern, Datum, Kennung, Arzt, Eintragung) VALUES (?,?,?,?,?)", self.current_patient.Intern, datum, 'T', '', notiz_eintr)
                c.commit()
                self.log.info("INSERT INTO Kassenkartei: Intern='%s' Datum='%s' Kennung='%s', Eintrag='%s'", self.current_patient.Intern, datum, 'T', notiz_eintr)

            self.state = 'start'

s = astm.server.Server(dispatcher=Dispatcher, host='0.0.0.0', port=1245, request=RequestHandler)
s.serve_forever()
