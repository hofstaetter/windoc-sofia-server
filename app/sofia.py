
from astm.mapping import (
        Component, ConstantField, ComponentField, DateField, DateTimeField,
        IntegerField, SetField, TextField, NotUsedField
        )
from astm.records import (
        HeaderRecord, PatientRecord, OrderRecord, ResultRecord, CommentRecord,
        TerminatorRecord
        )

Sender = Component.build(
        TextField(name='name'),
        TextField(name='version')
        )
Test = Component.build(
        NotUsedField(name='_'),
        NotUsedField(name='__'),
        NotUsedField(name='___'),
        TextField(name='analyte_name', required=True)
        )

class Header(HeaderRecord):
    sender = ComponentField(Sender)
    processing_id = ConstantField(default='P')
    version = TextField(name='version', default='E 1394-97')

class Patient(PatientRecord):
    practice_id = TextField(name='practice_id', required=True)
    location = TextField(name='location')

class Order(OrderRecord):
    sample_id = TextField(name='sample_id')
    test = TextField(name='test')
    collector = TextField(name='collector')
    biomaterial = TextField(name='biomaterial')

class Comment(CommentRecord):
    data = TextField(name='data', required=True)

class Result(ResultRecord):
    test = ComponentField(Test)
    value = TextField(name='value', required=True)
    units = TextField(name='units')
    references = TextField(name='references')
    abnormal_flag = TextField(name='abnormal_flag')
    status = TextField('status', required=True)
    completed_at = DateTimeField(name='completed_at', required=True)

Terminator = TerminatorRecord

WRAPPER_DICT = {
        'H' : Header,
        'P' : Patient,
        'O' : Order,
        'C' : Comment,
        'R' : Result,
        'L' : Terminator
        }
