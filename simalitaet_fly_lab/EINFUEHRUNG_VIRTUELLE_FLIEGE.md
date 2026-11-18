# Wie bringen wir einer virtuellen Fliege bei, eine Welt wahrzunehmen?

*Eine allgemein verständliche Einführung in `SIMALITAET_FLY_LAB` und das Testuniversum Seestraße 43*

---

Stellen Sie sich ein gewöhnliches Wohnhaus vor — ein Erdgeschoss mit offener Küche, ein Wohnzimmer mit großem Südfenster, eine kühle, dunkle Speisekammer hinter einer angelehnten Tür, ein warmes Dachstudio und ein feuchtes Badezimmer im Obergeschoss. Auf dem Küchentisch liegt eine Obstschale mit reifen Bananen, daneben steht ein Biomülleimer, oben im Bad liegt ein feuchter Schwamm am Waschbecken.

Wenn eine echte Fruchtfliege (*Drosophila melanogaster*) durch das offene Treppenhaus dieses Hauses fliegt, folgt sie keinem vorprogrammierten Drehbuch. Niemand hat ihr eine Liste mit Koordinaten gegeben: *„Fliege nach Punkt X = 8,85, Y = 3,35.“* Sie nimmt stattdessen in jedem Augenblick Luftströmungen, Licht, winzige Duftmoleküle und Wände wahr — und entscheidet auf Basis eines gerade einmal stecknadelkopfgroßen Gehirns, wohin der nächste Flügelschlag geht.

Genau das wollen wir in **SIMALITAET_FLY_LAB** erforschen. Nicht als Film und nicht als Trick, sondern als überprüfbares wissenschaftliches Labor.

---

## 1. Was ist ein Konnektom?

Wenn man eine Brücke verstehen will, schaut man sich ihren Bauplan an. Wenn man ein Gehirn verstehen will, braucht man seinen **Schaltplan** — die Karte aller Nervenzellen und ihrer Verbindungen. Diesen vollständigen Verdrahtungsplan nennt man **Konnektom**.

Dank internationaler Forschungsprojekte wie **FlyWire** kennen wir heute das komplette Gehirn einer erwachsenen Fruchtfliege auf Elektronenmikroskop-Ebene:
- Rund **138.639 einzelne Nervenzellen** (in unserem Datensatz exakt vermessen),
- verbunden durch über **15 Millionen gerichtete Leitungen** und mehr als **54 Millionen Synapsen**.

Zum ersten Mal in der Geschichte liegt für ein sehendes, fliegendes und riechendes Tier ein vollständiger Schaltplan vor. In `SIMALITAET_FLY_LAB` erfinden wir keine Fantasie-Verbindungen: Unser Modell lädt genau diesen echten biologischen Schaltplan.

---

## 2. Wie funktionieren Nervenzellen?

Man kann sich eine einzelne Nervenzelle (**Neuron**) wie einen kleinen elektrischen Speicher mit einem Überlauf vorstellen:

1. Über ihre Eingänge (Synapsen) empfängt sie ständig winzige Signale von anderen Zellen oder von Sinnesorganen.
2. Manche Signale laden die Zelle elektrisch auf (**erregend**, z. B. durch den Botenstoff Acetylcholin). Andere Signale bremsen sie wieder herunter (**hemmend**, z. B. durch GABA oder Glutamat).
3. Überschreitet die Spannung in der Zelle eine bestimmte Schwelle, gibt sie einen kurzen Impuls weiter — ein **Aktionspotenzial („Spike“)**.

Eine einzelne Zelle „versteht“ noch gar nichts. Aber wenn Tausende spezialisierte Zellen miteinander verschaltet sind — Riechzellen mit Auswertungszentren, Sehzellen mit Ausweichschaltungen — entstehen daraus sinnvolle Reaktionen: Links riecht es stärker nach überreifer Banane als rechts? Dann feuern die linken Riechzellen häufiger als die rechten, und am Ausgang entsteht ein Drehimpuls nach links.

---

## 3. Wie wird aus neuronalen Signalen Bewegung?

Zwischen Gehirn und Körper sitzt eine Art Datenkabel im Hals der Fliege: sogenannte **absteigende Neuronen** (*Descending Neurons*, kurz `DN`). Im echten FlyWire-Datensatz sind das zum Beispiel exakt vier Zellen namens `DNa01` und `DNa02` (zwei links, zwei rechts), die Lenksignale transportieren, `DNp09` für Vorwärtsbewegung oder `DNp01` für einen plötzlichen Fluchtsprung.

Wenn in unserem virtuellen Fliegengehirn zum Beispiel ein Wand-Detektor im Facettenauge (`LC4` / `LPLC2`) erkennt, dass links eine Wand schnell näher kommt, hemmt das Netzwerk den Vorwärtstrieb und kippt das Gleichgewicht zwischen linken und rechten Lenkneuronen. Dieses Ungleichgewicht übersetzt unsere **Body Engine** in echte physikalische Drehmomente im Flug oder in Beinkoordination beim Laufen.

Beim Laufen steuert ein rhythmischer Taktgeber (**Tripod-CPG**) immer abwechselnd drei Beine gleichzeitig — links vorne, rechts mitte, links hinten — sodass die Fliege jederzeit stabil auf drei Beinen steht, während die anderen drei Beine vorschwingen.

---

## 4. Warum braucht ein simuliertes Lebewesen einen Körper?

Ein reines Computerprogramm ohne Körper und Umwelt kennt keine Konsequenzen. Wenn ein bloßes Text-Programm eine Entscheidung berechnet, verändert sich danach seine physikalische Perspektive nicht.

Bei einer **verkörperten Simulation** im Haus *Seestraße 43* ist das völlig anders — es entsteht ein **geschlossener Regelkreis**:

> **Umwelt → Sinnesorgane → Gehirn (Konnektom) → Muskeln/Flügel → Körperbewegung → neue Sinneseindrücke**

Wenn sich unsere Fliege nach rechts dreht:
- verschiebt sich das Licht des Südfensters vom rechten auf das linke Facettenauge,
- ändert sich die relative Windrichtung an den Fühlern,
- verändert sich der Duftunterschied zwischen linker und rechter Antenne,
- nähert sich vielleicht plötzlich der Türrahmen der Speisekammer.

Ihr eigenes Verhalten verändert also direkt, was sie 10 Millisekunden später erlebt. Ohne Körper gäbe es diese Rückkopplung nicht — und genau in dieser Rückkopplung liegt der Unterschied zwischen einer Abspiel-Animation und echtem Verhalten.

---

## 5. Wie kann sie aus ihrer Umwelt lernen?

Die Fliege bringt zwei Dinge mit:

1. **Angeborene Reflexe:** Bestimmte Gerüche (wie *Geosmin*, das typische Warnsignal für Schimmel und Bakterien am feuchten Schwamm im Bad) aktivieren einen festen Schaltkreis (`DA2`), der die Fliege instinktiv abdrehen lässt. Zucker hingegen belohnt sofort beim Schmecken über die Füße.
2. **Kurzzeit-Lernen im Pilzkörper (Mushroom Body):** Im Fliegengehirn gibt es rund 5.000 sogenannte *Kenyon-Zellen*. Sie codieren, *welcher* Duft gerade in der Luft liegt. Kommt gleichzeitig ein Warnsignal über spezielle Dopamin-Zellen (`PPL1` — etwa wenn die Fliege auf einem bitteren Köder landet), schwächt diese **3-Faktor-Regel** (*Geruch + Bestrafung → Verhaltensänderung*) die Verbindung zum Annäherungs-Ausgang ab.

Zehn Sekunden später erinnert sich die Fliege an diesen negativen Reiz und hebt sofort ab, statt von der Banane zu trinken. **Aber:** Dieses Kurzzeitgedächtnis verblasst in unserem Modell bewusst innerhalb von Minuten (`~30 Minuten` komplett vergessen). Wir bauen kein künstliches Langzeitgedächtnis ein, solange die biologischen Konsolidierungsmechanismen dafür nicht sauber nachgewiesen sind.

---

## 6. Was können wir damit erforschen?

In der deterministischen Nachbildung der **Seestraße 43** können wir Versuche unter absolut identischen physikalischen Bedingungen wiederholen und gezielt vergleichen:
- **Ablationen („Was fehlt ohne Teil X?“):** Was passiert, wenn wir genau die Seh-Neuronen stumm schalten, eine Antenne blockieren oder die Geosmin-Warnleitung kappen?
- **Entscheidungskonflikte:** Was wählt eine durstige Fliege, wenn Wasser am Waschbecken zusammen mit abschreckendem Geosmin auftritt?
- **Klima- und Raumwirkung:** Wie findet ein Tier durch ein offenes Treppenhaus aus dem Obergeschoss in die Küche oder unter einem `1,5 cm` schmalen Türspalt hindurch zu überreifen Birnen?

---

## 7. Was wissen wir ausdrücklich noch nicht?

Ehrliche Wissenschaft benennt ihre Grenzen genauso klar wie ihre Erfolge:

- **Kein Bewusstsein:** Unser Modell zeigt kein Empfinden, kein subjektives Erleben und kein Bewusstsein — und behauptet auch keines.
- **Unvollständige Zellphysiologie:** Ein Elektronenmikroskop zeigt, *wer* mit *wem* verbunden ist, aber nicht direkt jede elektrische Membraneigenschaft jeder einzelnen Zelle. Für Zeitkonstanten und Auslöseschwellen nutzen wir deshalb vereinfachte mathematische Modellannahmen.
- **Fehlendes Bauchmark im Primärdatensatz:** FlyWire `v783` kartiert das Gehirn bis in den Hals, noch nicht die detaillierten Bein- und Flügelmotoneuronen im Brustmark (dafür ist bereits die Schnittstelle zum neueren Datensatz *MaleCNS* vorbereitet).
- **Wetter & Innenraum als Approximation:** Unser `0,25 m`-Voxelgitter bildet Luftströmungen und Duftfahnen physikalisch plausibel ab, ersetzt aber keine voll aufgelöste Millionen-Zellen-Turbulenzsimulation (CFD).

Kurz gesagt: Wir haben keine lebendige Fliege erschaffen. Wir haben ein transparentes, überprüfbares Forschungsinstrument gebaut, an dem man Schritt für Schritt beobachten kann, wie ein biologischer Bauplan, ein kleiner Körper und eine echte 3D-Welt zusammenspielen.
