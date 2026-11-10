# Kindersicherung für Home Assistant

[![Tests](https://github.com/patrickbrundiers-dev/Kindersicherung/actions/workflows/tests.yaml/badge.svg)](https://github.com/patrickbrundiers-dev/Kindersicherung/actions/workflows/tests.yaml)
[![Validate](https://github.com/patrickbrundiers-dev/Kindersicherung/actions/workflows/validate.yaml/badge.svg)](https://github.com/patrickbrundiers-dev/Kindersicherung/actions/workflows/validate.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Wird ein Fernseher eingeschaltet, muss innerhalb weniger Sekunden bestätigt werden (Schalter, Button in der Handy-Benachrichtigung oder ein vorhandener Schalter). Sonst wird der Fernseher wieder ausgeschaltet. Nach mehreren Fehlversuchen sind die Fernseher für eine einstellbare Zeit gesperrt.

Die Integration ersetzt die Automationen „Kindersicherung TV Wohnzimmer“ samt Sperr-Automation, Zähler, Timer und Bestätigungs-Helfer. **Alles wird im Editor eingestellt**, es ist kein YAML nötig.

## Installation über HACS

1. HACS öffnen, oben rechts Menü, **Benutzerdefinierte Repositories**.
2. Repository `https://github.com/patrickbrundiers-dev/Kindersicherung` hinzufügen, Kategorie **Integration**.
3. „Kindersicherung“ herunterladen und Home Assistant neu starten.
4. **Einstellungen, Geräte & Dienste, Integration hinzufügen, Kindersicherung**.

Pro Einrichtung entsteht ein Gerät mit eigener Sperre. Du kannst die Integration mehrfach hinzufügen, z. B. für jeden Fernseher einzeln mit eigenen Zeiten.

## Einstellungen

Beim **Einrichten** fragt die Integration nur das Nötigste ab: Name, Fernseher, Handy-Benachrichtigung, Zahlencode, Zeitfenster und gesperrte Apps.

Unter **Konfigurieren** öffnet sich ein Menü mit fünf Bereichen, die jeweils für sich gespeichert werden:

1. **Fernseher und Benachrichtigungen**
2. **Zeitfenster, Ferien und Vorwarnung** (inkl. zweitem Zeitfenster)
3. **Gesperrte Apps** (z. B. YouTube, Freigabedauer)
4. **Tageslimit**
5. **Code, Bestätigung und Sperre**

Die häufigsten Werte lassen sich außerdem direkt auf der Geräteseite oder im Dashboard ändern, ohne den Editor zu öffnen: **Sperre ab** und **Sperre bis** (`time`), **Tageslimit**, **Dauer App-Freigabe** und **Vorwarnung**, **Dauer Strafe** (`number`, Schieberegler) sowie **Apps immer sperren** (`switch`). Diese Änderungen wirken sofort, ohne die Integration neu zu laden.

| Einstellung | Bedeutung |
|---|---|
| Fernseher | Ein oder mehrere Media Player. Die Auswahl erfolgt direkt aus deinen Geräten. |
| notify-Dienste | Dienste wie `mobile_app_patrick`. Mit aktivierter Option erscheint ein **Bestätigen-Button** in der Benachrichtigung. Läuft die Zeit ab, verschwindet die Anfrage vom Handy, ein zu spät gedrückter Button gibt nichts frei. Anfragen, App-Hinweise und Infos ersetzen sich auf dem Handy nicht gegenseitig. |
| notify-Entitäten | Entitäten für `notify.send_message`, z. B. eine Sprachausgabe im Wohnzimmer. |
| Nur wenn zu Hause | Optional: `person` oder `device_tracker`. Ist keine davon zu Hause, wird jeder eingeschaltete Fernseher sofort ausgeschaltet (Status *Niemand zu Hause*). **Heute erlauben** hebt das auf. Unbekannt oder nicht verfügbar zählt als zu Hause, damit ein Neustart nicht sperrt. |
| Zusätzliche Bestätigungs-Schalter | Optional: vorhandene `input_boolean` oder Schalter, die ebenfalls bestätigen können (z. B. dein bisheriger Schalter, damit Dashboards weiter funktionieren). |
| Zahlencode (optional) | 4 bis 12 Ziffern, den du selbst festlegst. Ist ein Code gesetzt, bestätigst du nur noch über das Feld **Code eingeben** (Entität `text`, z. B. im Dashboard oder in der App) oder den Bestätigen-Button auf dem Handy. Der Bestätigungs-Schalter und zusätzliche Schalter zählen dann nicht mehr. Ein falscher Code beendet die Abfrage sofort, schaltet den Fernseher aus und zählt als Fehlversuch. Der Code liegt im Klartext in der Konfiguration von Home Assistant. |
| Nachricht | Text der Benachrichtigung. |
| Hinweis bei Sperre | Bei Sperre geht eine Nachricht an alle Ziele („gesperrt bis 17:42 Uhr“). Wird währenddessen ein Fernseher eingeschaltet, sagen die notify-Entitäten (z. B. Sprachausgabe) die Sperrzeit an, höchstens einmal pro Minute. |
| Aktiv ab / bis, Wochentage | Zeitfenster der Abfrage. Gleiche Start- und Endzeit bedeutet ganztägig, Start nach Ende ein Fenster über Mitternacht. Bei einem Fenster über Mitternacht zählt der Morgen zum Wochentag des Abends: 21:00 bis 07:30 mit Sonntag bis Donnerstag sperrt Sonntagabend bis Freitagmorgen, Freitagabend bleibt frei. Sonst bezieht sich der Wochentag auf den aktuellen Tag. Standard: 00:00 bis 19:00 an allen Tagen. |
| Wenn bei Beginn der Regeln ein Fernseher läuft | *Ausschalten*, *Bestätigung verlangen* oder *Weiterlaufen lassen*. Gilt zu „Aktiv ab“ und wenn eine Ausnahme oder Pause endet, auch nach einem Neustart oder Verbindungsaussetzer um diese Zeit. Ältere Einträge übernehmen den früheren Schalter „Bei Beginn ausschalten“ (an = Ausschalten, aus = Weiterlaufen lassen), neue Einträge verlangen eine Bestätigung. |
| Zweites Zeitfenster | Optional, z. B. am Wochenende 22:30 bis 08:00. Ohne gewählte Wochentage ist es aus. |
| Gesperrte Apps | Teil des App-Namens oder der App-ID, Vorauswahl bei neuen Einträgen: `youtube`. Die App wird sofort beendet, auch nach einer normalen Bestätigung. Bei Android TV drückt die Integration Home auf der zugehörigen `remote`-Entität, ohne Fernbedienungs-Entität wird der Fernseher ausgeschaltet. |
| Gesperrte Apps immer beenden | An (Standard bei neuen Einträgen): jederzeit. Aus: nur im Zeitfenster. Freigabe mit dem Zahlencode im Feld **Code eingeben**, mit **App freigeben** in der Handy-Benachrichtigung (kommt, sobald eine App beendet wurde) oder durch eine Bestätigung per Code bzw. Handy. Ein falscher Code zählt als Fehlversuch. |
| Erlaubte Apps | Ausnahmen von der App-Sperre, z. B. `tvkids` für YouTube Kids, obwohl `youtube` gesperrt ist. |
| Dauer einer App-Freigabe | Standard 60 Minuten. |
| Zeitfenster aussetzen, wenn an | Kalender (z. B. Schulferien), `input_boolean` oder `binary_sensor`. Solange eine davon an ist, gelten die Zeitfenster nicht. Tageslimit und Sperre bleiben. |
| Nur vor Schultagen | Das erste Zeitfenster gilt nur am Abend vor einem Schultag (Beginn ab 12 Uhr, z. B. 21:00 bis 07:30) bzw. an Schultagen (Beginn vormittags). Die Wochentage zählen dann nicht. So bleibt der Abend vor einem Feiertag oder vor den Ferien frei, und der letzte Ferienabend vor Schulbeginn ist gesperrt. |
| Werktag-Sensor | Optional: `binary_sensor` der Workday-Integration. Die Integration fragt ihn mit `workday.check_date` für jeden einzelnen Tag ab. Ohne Sensor gilt Montag bis Freitag. |
| Kalender mit Schulferien | Optional: jeder Termin darin ist ein Ferientag (kein Schultag, Tageslimit für Ferien). Die Kalender werden alle 30 Minuten neu gelesen. |
| Vorwarnung | Minuten vor Beginn des Zeitfensters und vor Ende des Tageslimits, wenn ein Fernseher läuft. 0 = aus. |
| Tageslimit Bildschirmzeit | Minuten pro Tag über alle Fernseher des Eintrags. Läuft nur der Bildschirmschoner (z. B. Google TV „dreamx“), zählt die Minute nicht. Ist es erreicht, wird ausgeschaltet, und bis Mitternacht muss jedes Einschalten bestätigt werden. 0 = aus. |
| Tageslimit Samstag und Sonntag, Tageslimit in den Ferien | Optional. Leer = wie an anderen Tagen, 0 = kein Limit. Ferien (Ferienkalender oder Pause-Entität an) gehen vor dem Wochenende. |
| Bonuszeit pro Druck | Standard 30 Minuten, siehe Button **Bonuszeit**. |
| Zeit zum Bestätigen | Standard 30 Sekunden. |
| Bestätigung gilt | 0 (Standard) = bis der Fernseher länger aus ist. Sonst so viele Minuten, danach (mit Vorwarnung) neue Abfrage, ohne Antwort geht der Fernseher aus. |
| Fehlversuche bis zur Sperre | Standard 3. |
| Dauer der Sperre | Standard 30 Minuten. |
| Fehlversuche verfallen nach | Standard 60 Minuten, 0 bedeutet nie. |
| Dauer der Strafe | Wie lange der Button **Strafe** sperrt. Standard 24 Stunden, 1 bis 168. |

## Entitäten (pro Gerät)

- `switch` **Kindersicherung aktiv**: schaltet alles ein oder aus (ersetzt „Automation aus“).
- `switch` **Bestätigung**: zum Bestätigen einschalten (ohne Zahlencode). Das Attribut `waiting` zeigt, ob gerade gewartet wird.
- `text` **Code eingeben**: nur mit eingestelltem Zahlencode vorhanden. Der Zustand bleibt immer leer.
- `binary_sensor` **Gesperrt** mit den Attributen `lock_until`, `attempts`, `max_attempts`.
- `sensor` **Fehlversuche** und **Gesperrt bis** (Zeitstempel).
- `sensor` **Statistik**: *Bestätigungen*, *Zeitüberschreitungen*, *Falsche Codes*, *Sperren* und *Apps beendet* als Gesamtzähler. Sie speichern Langzeitstatistik, im Dashboard zeigt eine „Statistik-Diagramm“-Karte (Statistic graph card) mit Zeitraum „Woche“ oder „Tag“ die Summen pro Zeitraum.
- `sensor` **Status**: Zustand auf einen Blick, *Frei*, *Sperrzeit*, *Sperrzeit pausiert*, *Gesperrt*, *Ausnahme*, *Tageslimit erreicht*, *Bonuszeit* oder *Aus*. Die Attribute zeigen, bis wann eine Sperre oder Ausnahme gilt (`until`), ob Apps gerade gesperrt sind (`apps_blocked`) die Bildschirmzeit heute, das heutige Tageslimit und ob heute Ferien sind. Gut geeignet als erste Zeile einer Dashboard-Karte.
- `button` **Entsperren** und **Jetzt sperren**.
- `button` **Strafe**: sperrt alle Fernseher des Eintrags für die eingestellte Dauer (Standard 24 Stunden), auch außerhalb des Zeitfensters. Jedes Einschalten wird sofort rückgängig gemacht, eine Ausnahme oder App-Freigabe endet. Eine längere laufende Sperre wird nicht verkürzt. Nur **Entsperren** hebt die Strafe vorher auf. Die Sperre übersteht einen Neustart.
- `button` **Heute erlauben**: setzt Zeitfenster, App-Sperre und Tageslimit bis Mitternacht aus, bzw. bis zum Ende eines Fensters, das heute noch läuft oder beginnt (bei 21:00 bis 07:30 also bis zum nächsten Morgen). **Ausnahme beenden** hebt das wieder auf, ebenso eine App-Freigabe. Eine Sperre nach Fehlversuchen bleibt bestehen.
- `button` **Bonuszeit**: verlängert das Tageslimit heute um die eingestellten Minuten und erlaubt in der Sperrzeit so lange Fernsehen ohne Abfrage (gesperrte Apps bleiben gesperrt, wenn sie immer gesperrt sind). Mehrmals drücken verlängert weiter. Kurz vor Ende kommt die Vorwarnung. Dauer im Dashboard über **Bonuszeit** (`number`), ebenso **Bestätigung gilt**.
- `sensor` **Ausnahme bis** und **Apps freigegeben bis** (Zeitstempel) und **Bildschirmzeit heute** (Minuten, mit `daily_limit` und `limit_reached`).
- `binary_sensor` **Regeln aktiv**: an, solange Zeitfenster oder Tageslimit gelten (Attribute `in_window`, `paused`, `exception_active`, `limit_reached`).

## So wird geprüft

Die Kindersicherung schaut auf den Zustand der Fernseher, nicht nur auf den Moment des Einschaltens. Bei jeder Änderung und jede Minute gilt: Läuft ein Fernseher, während Regeln gelten, und ist er für diese Sitzung nicht freigegeben, wird nachgefragt (bzw. bei Sperre ausgeschaltet). Das deckt auch Fernseher ab, die aus „nicht verfügbar“ angehen, beim Start von Home Assistant schon laufen oder um „Aktiv ab“ kurz nicht erreichbar sind.

Eine Bestätigung gilt, bis der Fernseher länger als 2 Minuten aus oder nicht verfügbar war. Kurzes Flackern zwischen „aus“ und „nicht verfügbar“ (typisch für Android TV) beendet sie nicht. Enden die Regeln (z. B. um „Aktiv bis“), endet auch die Freigabe.

Beim Ausschalten wartet die Integration bis zu 10 Sekunden auf den neuen Zustand, bevor sie es noch einmal versucht. Bei Android TV ist Ausschalten die Power-Taste, ein zu früher zweiter Druck würde den Fernseher wieder einschalten. Nach der Home-Taste für eine gesperrte App prüft sie nach 5 Sekunden, ob die App noch läuft, und schaltet sonst den Fernseher aus. Läuft während einer Abfrage ein zweiter Fernseher des Eintrags an, gilt die Abfrage für beide.

Jede Aktion steht mit Grund im **Logbuch** („hat den Fernseher ausgeschaltet (keine Bestätigung)“). Unter Geräte & Dienste gibt es einen **Diagnose-Download** mit Einstellungen (ohne Code) und aktuellem Zustand.

## Ereignisse für eigene Automationen

`kindersicherung_action` (mit `action` = `turn_off` oder `close_app`, `reason` und `entity_id`), `kindersicherung_confirmed`, `kindersicherung_failed` (mit `attempts`, `max_attempts`, `reason` = `timeout` oder `wrong_code`), `kindersicherung_locked` (mit `lock_until`), `kindersicherung_unlocked`. Alle enthalten `entry_id` und `name`.

## Unterschiede zur bisherigen Automation

- Die Sperre überlebt einen Neustart von Home Assistant (der Timer-Helfer tat das nicht).
- Während der Sperre wird jedes Einschalten sofort verhindert, auch außerhalb des Zeitfensters.
- Fehlversuche verfallen nach einer Stunde, statt über Tage stehen zu bleiben.
- Eltern bekommen eine Nachricht, sobald gesperrt wird, und im Raum wird bei Einschaltversuchen die Sperrzeit angesagt.
- Reagiert der Fernseher nicht auf das Ausschalten, wird bis zu dreimal im Abstand von 3 Sekunden wiederholt.
- Ausgeschaltet wird über die Media-Player-Entität, nicht über eine Geräte-ID.

## Migration

Nach dem Einrichten und einem Test können die alten Automationen („Kindersicherung TV Wohnzimmer“, „Kindersicherung TV Wohnzimmer 2“, „TV Wohnzimmer: Sperre blockt Einschalten“) und die Helfer `input_boolean.kindersicherung_tv`, `counter.counter_tv_kindersicherung_fehlversuche`, `timer.timer_tv_kindersicherung_sperre` gelöscht werden. Wer den alten Schalter in Dashboards weiter nutzen will, trägt ihn unter „Zusätzliche Bestätigungs-Schalter“ ein.

## Entwicklung

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt ruff
pytest          # Tests (Logik, Ablauf, Übersetzungen)
ruff check .    # Lint
```

Aufbau von `custom_components/kindersicherung/`:

| Datei | Inhalt |
|---|---|
| `controller.py` | Ablauf: Einschalten erkennen, Bestätigung, Sperre, Zeitfenster, App-Sperre, Tageslimit |
| `logic.py` | Reine Zeit- und Zählerlogik ohne Home Assistant, in `tests/test_logic.py` getestet |
| `config_flow.py` | Einrichtung und Menü unter **Konfigurieren** |
| `binary_sensor.py`, `sensor.py`, `switch.py`, `button.py`, `number.py`, `time.py`, `text.py` | Entitäten, alle über `entity.py` an den Controller gebunden |
| `translations/`, `icons.json` | Texte (de, en) und Icons, gleiche Schlüssel werden in `tests/test_translations.py` geprüft |

Auf GitHub laufen bei jedem Pull Request und auf `main` die Tests, Ruff, hassfest und die HACS-Prüfung, hassfest und HACS zusätzlich jeden Montag. Für eine neue Version die `version` in `manifest.json` erhöhen.
