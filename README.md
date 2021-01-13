
# sofia-server

Ein Server der die LIS requests des Sofia Geräts entgegen nehmen kann und im Windoc einträgt.

## Files

### sofia.py

Enthält die ASTM Wrapper-Klassen für die Sofia-Implementation des ASTM Standards.

### sofia_server.py

Benutzt ASTM Pip Module und sofia.py um daraus einen ASTM Server zu machen.
Hier passieren auch die DB-Zugriffe.

### send.py

Ein kleines Utility Skript um einen Binary Dump von einem Sofia Gerät an den Server zu senden.
Mit dem ganzen zugehörigen ACK-NAK-Pipapo.
