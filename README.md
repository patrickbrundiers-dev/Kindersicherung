# Kindersicherung für Home Assistant

Wird ein Fernseher eingeschaltet, muss innerhalb weniger Sekunden bestätigt werden (Schalter, Button in der Handy-Benachrichtigung oder ein vorhandener Schalter). Sonst wird der Fernseher wieder ausgeschaltet. Nach mehreren Fehlversuchen sind die Fernseher für eine einstellbare Zeit gesperrt.

Die Integration ersetzt die Automationen „Kindersicherung TV Wohnzimmer“ samt Sperr-Automation, Zähler, Timer und Bestätigungs-Helfer. **Alles wird im Editor eingestellt**, es ist kein YAML nötig.

## Installation über HACS

1. HACS öffnen, oben rechts Menü, **Benutzerdefinierte Repositories**.
2. Repository `https://github.com/patrickbrundiers-dev/Kindersicherung` hinzufügen, Kategorie **Integration**.
3. „Kindersicherung“ herunterladen und Home Assistant neu starten.
4. **Einstellungen, Geräte & Dienste, Integration hinzufügen, Kindersicherung**.

Pro Einrichtung entsteht ein Gerät mit eigener Sperre. Du kannst die Integration mehrfach hinzufügen, z. B. für jeden Fernseher einzeln mit eigenen Zeiten.

## Einstellungen (Einrichtung und „Konfigurieren“)

| Einstellung | Bedeutung |
|---|---|
| Fernseher | Ein oder mehrere Media Player. Die Auswahl erfolgt direkt aus deinen Geräten. |
| notify-Dienste | Dienste wie `mobile_app_patrick`. Mit aktivierter Option erscheint ein **Bestätigen-Button** in der Benachrichtigung. |
| notify-Entitäten | Entitäten für `notify.send_message`, z. B. eine Sprachausgabe im Wohnzimmer. |
| Zusätzliche Bestätigungs-Schalter | Optional: vorhandene `input_boolean` oder Schalter, die ebenfalls bestätigen können (z. B. dein bisheriger Schalter, damit Dashboards weiter funktionieren). |
| Nachricht | Text der Benachrichtigung. |
| Hinweis bei Sperre | Bei Sperre geht eine Nachricht an alle Ziele („gesperrt bis 17:42 Uhr“). Wird währenddessen ein Fernseher eingeschaltet, sagen die notify-Entitäten (z. B. Sprachausgabe) die Sperrzeit an, höchstens einmal pro Minute. |
| Aktiv ab / bis, Wochentage | Zeitfenster der Abfrage. Gleiche Start- und Endzeit bedeutet ganztägig, Start nach Ende ein Fenster über Mitternacht. Der Wochentag bezieht sich auf den aktuellen Tag. Standard: 00:00 bis 19:00 an allen Tagen. |
| Zeit zum Bestätigen | Standard 30 Sekunden. |
| Fehlversuche bis zur Sperre | Standard 3. |
| Dauer der Sperre | Standard 30 Minuten. |
| Fehlversuche verfallen nach | Standard 60 Minuten, 0 bedeutet nie. |

## Entitäten (pro Gerät)

- `switch` **Kindersicherung aktiv**: schaltet alles ein oder aus (ersetzt „Automation aus“).
- `switch` **Bestätigung**: zum Bestätigen einschalten. Das Attribut `waiting` zeigt, ob gerade gewartet wird.
- `binary_sensor` **Gesperrt** mit den Attributen `lock_until`, `attempts`, `max_attempts`.
- `sensor` **Fehlversuche** und **Gesperrt bis** (Zeitstempel).
- `button` **Entsperren** und **Jetzt sperren**.

## Ereignisse für eigene Automationen

`kindersicherung_confirmed`, `kindersicherung_failed` (mit `attempts`, `max_attempts`), `kindersicherung_locked` (mit `lock_until`), `kindersicherung_unlocked`. Alle enthalten `entry_id` und `name`.

## Unterschiede zur bisherigen Automation

- Die Sperre überlebt einen Neustart von Home Assistant (der Timer-Helfer tat das nicht).
- Während der Sperre wird jedes Einschalten sofort verhindert, auch außerhalb des Zeitfensters.
- Fehlversuche verfallen nach einer Stunde, statt über Tage stehen zu bleiben.
- Eltern bekommen eine Nachricht, sobald gesperrt wird, und im Raum wird bei Einschaltversuchen die Sperrzeit angesagt.
- Reagiert der Fernseher nicht auf das Ausschalten, wird bis zu dreimal im Abstand von 3 Sekunden wiederholt.
- Ausgeschaltet wird über die Media-Player-Entität, nicht über eine Geräte-ID.

## Migration

Nach dem Einrichten und einem Test können die alten Automationen („Kindersicherung TV Wohnzimmer“, „Kindersicherung TV Wohnzimmer 2“, „TV Wohnzimmer: Sperre blockt Einschalten“) und die Helfer `input_boolean.kindersicherung_tv`, `counter.counter_tv_kindersicherung_fehlversuche`, `timer.timer_tv_kindersicherung_sperre` gelöscht werden. Wer den alten Schalter in Dashboards weiter nutzen will, trägt ihn unter „Zusätzliche Bestätigungs-Schalter“ ein.
