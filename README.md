
# Sofia COVID-19 Server Integrator für Windoc

Ein Server der die LIS requests des Sofia Geräts entgegen nehmen kann und im Windoc einträgt. Der Server wird als Docker Container deployed und horcht standardmäßig auf Port `1245`.

Die Anwendung empfängt 1.) den ASTM Datenstream des [Sofia 2 Fluorescent Immunoassay Analyzer](https://www.quidel.com/immunoassays/sofia-tests-kits/sofia-2-analyzer) von Quidel (COVID-19/Influenza Schnelltests), wertet die Results aus, und schreibt diese automatisch in die Pervasive SQL Datenbank der [Ärztesoftware Windoc](https://www.edv-klein.at/). Beim Eintragen der Ergebnisse wird weiters auf eine etwaige Leistungszuordnung (Laborschablone) und Mapping der Versicherungsträger Rücksicht genommen.

## Files

### sofia.py

Enthält die ASTM Wrapper-Klassen für die Sofia-Implementation des ASTM Standards.

### sofia_server.py

Benutzt ASTM Pip Module und sofia.py um daraus einen ASTM Server zu machen.
Hier passieren auch die DB-Zugriffe.

### send.py

Ein kleines Utility Skript um einen Binary Dump von einem Sofia Gerät an den Server zu senden.
Mit dem ganzen zugehörigen ACK-NAK-Pipapo.
