---
name: voice-buddy
description: "Configure CC voice companion - change style, nickname, enable/disable"
---

Help the user configure Voice Buddy (CC). The `voice-buddy` CLI is available in PATH (via the plugin's `bin/` directory).

Available actions:

1. **Show current config**: Run `voice-buddy config` to display current settings
2. **Change style**: Run `voice-buddy config --style <id>` where id is one of: cute-girl, elegant-lady, warm-boy, secretary, kawaii
3. **Change nickname**: Run `voice-buddy config --nickname "<name>"`
4. **Toggle events**: Run `voice-buddy config --disable <event>` or `--enable <event>` where event is: sessionstart, sessionend, notification, stop
5. **On/Off**: Run `voice-buddy on` or `voice-buddy off`
6. **Edit persona**: Run `voice-buddy config --edit-persona`
7. **Test**: Run `voice-buddy test <event>` to hear a sample (events: sessionstart, sessionend, notification, stop)

Ask the user what they'd like to configure, then run the appropriate command via Bash.
